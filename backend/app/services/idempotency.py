"""
Idempotency domain service for SmartCart 2.0.
Coordinates deduplication records using PostgreSQL's composite primary key (customer_id, key).
Detects payload tampering, prevents concurrent double-submissions, and safely replays responses.
"""
import hashlib
import json
import re
from typing import Any, Dict, Optional, Tuple
from uuid import UUID
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ConflictError,
    IdempotencyConflictError,
    NotFoundError,
    ValidationError,
)
from app.models.outbox import IdempotencyKey
from app.repositories.idempotency import IdempotencyKeyRepository

KEY_REGEX = re.compile(r"^[A-Za-z0-9_-]{1,255}$")


class IdempotencyService:
    """Service managing request idempotency tracking and safe response replay."""

    def __init__(
        self,
        idempotency_repo: IdempotencyKeyRepository,
        session: Optional[AsyncSession] = None,
    ) -> None:
        self.idempotency_repo = idempotency_repo
        self.session = session or idempotency_repo.session

    def validate_key(self, key: str) -> None:
        """
        Validate that the client-supplied Idempotency-Key satisfies schema constraints:
        non-empty, maximum 255 characters, and URL/header safe [A-Za-z0-9_-].
        """
        if not key or not isinstance(key, str) or not KEY_REGEX.match(key):
            raise ValidationError(
                "Idempotency-Key header must be 1-255 characters consisting only of alphanumeric, underscore, or hyphen"
            )

    def compute_request_hash(self, payload: Any) -> str:
        """
        Compute a deterministic SHA-256 hex digest of the client request payload.
        Keys are sorted to produce a canonical representation independent of key ordering.
        Sensitive credentials (e.g. passwords, tokens) must never be passed into payload.
        """
        if isinstance(payload, bytes):
            raw_bytes = payload
        elif isinstance(payload, str):
            raw_bytes = payload.encode("utf-8")
        else:
            canonical_json = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
            raw_bytes = canonical_json.encode("utf-8")

        return hashlib.sha256(raw_bytes).hexdigest()

    async def get_record(self, customer_id: UUID, key: str) -> Optional[IdempotencyKey]:
        """Retrieve an idempotency record by composite key (customer_id, key)."""
        self.validate_key(key)
        return await self.idempotency_repo.get_by_customer_and_key(customer_id, key)

    async def start_idempotent_operation(
        self,
        customer_id: UUID,
        key: str,
        request_payload: Any,
    ) -> Tuple[IdempotencyKey, bool]:
        """
        Initiate or check an idempotent operation.
        Returns tuple: (record, is_replay).
        - If matching completed record exists: returns (record, True) allowing response replay.
        - If key exists with DIFFERENT payload: raises IdempotencyConflictError.
        - If key exists with same payload but operation is still pending (response is None): raises ConflictError.
        - If key does not exist: creates new pending record (response=None) inside a savepoint and returns (record, False).
        """
        self.validate_key(key)
        request_hash = self.compute_request_hash(request_payload)

        # 1. Check existing record
        existing = await self.get_record(customer_id, key)
        if existing is not None:
            if existing.request_hash != request_hash:
                raise IdempotencyConflictError(
                    "Idempotency key reused with a differing request body"
                )

            # Completed previously: replay cached response
            if existing.response is not None:
                return existing, True

            # In flight / pending
            raise ConflictError(
                "A request with this idempotency key is currently being processed"
            )

        # 2. Register pending idempotency key
        new_record = IdempotencyKey(
            customer_id=customer_id,
            key=key,
            request_hash=request_hash,
            order_id=None,
            response=None,
        )

        session = self.session

        async def _persist_pending() -> IdempotencyKey:
            session.add(new_record)
            await session.flush()
            return new_record

        try:
            if session.in_transaction():
                async with session.begin_nested():
                    return await _persist_pending(), False
            else:
                async with session.begin():
                    return await _persist_pending(), False
        except IntegrityError as exc:
            orig_msg = str(exc.orig) if hasattr(exc, "orig") and exc.orig else str(exc)
            if "foreign key" in orig_msg.lower() or "23503" in orig_msg or "not present in table" in orig_msg.lower():
                raise NotFoundError(f"Customer '{customer_id}' does not exist") from exc

            # Concurrent race condition on composite primary key (customer_id, key)
            recheck = await self.get_record(customer_id, key)
            if recheck is not None:
                if recheck.request_hash != request_hash:
                    raise IdempotencyConflictError(
                        "Idempotency key reused with a differing request body"
                    ) from exc
                if recheck.response is not None:
                    return recheck, True
            raise ConflictError(
                "A concurrent request with this idempotency key is currently being processed"
            ) from exc

    async def complete_idempotent_operation(
        self,
        customer_id: UUID,
        key: str,
        response_data: Dict[str, Any],
        order_id: Optional[UUID] = None,
    ) -> IdempotencyKey:
        """
        Attach the final response payload and optional order_id to a completed operation.
        Flushes to the current transaction without committing.
        """
        self.validate_key(key)
        record = await self.get_record(customer_id, key)
        if record is None:
            raise NotFoundError(
                f"Idempotency record for customer '{customer_id}' and key '{key}' not found"
            )

        record.response = response_data
        if order_id is not None:
            record.order_id = order_id

        await self.session.flush()
        return record

    async def fail_idempotent_operation(self, customer_id: UUID, key: str) -> None:
        """
        Remove a pending idempotency record if the business transaction failed before completion.
        Allows the client to retry with the same key without being locked out.
        """
        self.validate_key(key)
        record = await self.get_record(customer_id, key)
        if record is not None and record.response is None:
            await self.session.delete(record)
            await self.session.flush()
