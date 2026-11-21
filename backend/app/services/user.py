"""
User domain service for SmartCart 2.0.
Handles atomic customer registration, password hashing via Argon2id, profile retrieval/updates,
and administrator-only store manager assignments and account status updates.
"""
import inspect
from typing import Optional, Tuple
from uuid import UUID, uuid4
from sqlalchemy.exc import IntegrityError

from app.core.exceptions import (
    BadRequestError,
    DuplicateResourceError,
    ForbiddenError,
    NotFoundError,
)
from app.core.security import get_password_hash
from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.user import User
from app.repositories.customer import CustomerRepository
from app.repositories.store import StoreRepository
from app.repositories.user import UserRepository


class UserService:
    """Service handling user account lifecycle, customer registration, and admin assignments."""

    def __init__(
        self,
        user_repo: UserRepository,
        customer_repo: CustomerRepository,
        store_repo: Optional[StoreRepository] = None,
    ) -> None:
        self.user_repo = user_repo
        self.customer_repo = customer_repo
        self.store_repo = store_repo

    async def register_customer(
        self,
        email: str,
        password: str,
        full_name: str,
        phone: Optional[str] = None,
        address: Optional[str] = None,
    ) -> Tuple[User, Customer]:
        """
        Atomically register a new customer with CUSTOMER role and associated profile.
        Role is strictly locked to CUSTOMER; clients cannot specify roles or store assignments.
        Password is encrypted with Argon2id before persistence.
        Uses explicit transaction boundaries: wraps in nested savepoint if transaction is active,
        or opens a new transaction if none is active.
        """
        normalized_email = email.strip().lower()
        existing = await self.user_repo.get_by_email(normalized_email)
        if existing is not None:
            raise DuplicateResourceError(f"Email '{email}' is already registered")

        user_id = uuid4()
        customer_id = uuid4()
        password_hash = get_password_hash(password)

        user = User(
            id=user_id,
            email=normalized_email,
            full_name=full_name.strip(),
            password_hash=password_hash,
            role=UserRole.CUSTOMER,
            assigned_store_id=None,
            is_active=True,
        )
        customer = Customer(
            id=customer_id,
            user_id=user_id,
            phone=phone.strip() if phone else None,
            address=address.strip() if address else None,
        )

        session = self.user_repo.session

        async def _persist_records() -> Tuple[User, Customer]:
            session.add(user)
            session.add(customer)
            await session.flush()
            return user, customer

        try:
            in_tx = session.in_transaction()
            if inspect.iscoroutine(in_tx):
                in_tx = await in_tx

            if in_tx:
                cm = session.begin_nested()
                if inspect.iscoroutine(cm):
                    cm = await cm
                async with cm:
                    return await _persist_records()
            else:
                cm = session.begin()
                if inspect.iscoroutine(cm):
                    cm = await cm
                async with cm:
                    return await _persist_records()
        except IntegrityError as exc:
            raise DuplicateResourceError(
                "A user or customer profile with these details already exists"
            ) from exc

    async def get_user_by_id(self, user_id: UUID) -> User:
        """
        Retrieve a user account by primary key UUID.
        Raises NotFoundError if user does not exist.
        """
        user = await self.user_repo.get_by_id(user_id)
        if user is None:
            raise NotFoundError(f"User with id '{user_id}' not found")
        return user

    async def get_customer_profile(self, user_id: UUID) -> Tuple[User, Optional[Customer]]:
        """Retrieve user account and associated customer profile."""
        user = await self.get_user_by_id(user_id)
        customer = await self.customer_repo.get_by_user_id(user_id)
        return user, customer

    async def update_customer_profile(
        self,
        user_id: UUID,
        full_name: Optional[str] = None,
        phone: Optional[str] = None,
        address: Optional[str] = None,
    ) -> Tuple[User, Customer]:
        """
        Update user display name and customer contact details.
        Raises NotFoundError if customer profile does not exist.
        """
        user = await self.get_user_by_id(user_id)
        customer = await self.customer_repo.get_by_user_id(user_id)
        if customer is None:
            raise NotFoundError(f"Customer profile not found for user '{user_id}'")

        if full_name is not None and full_name.strip():
            user.full_name = full_name.strip()

        if phone is not None:
            customer.phone = phone.strip() if phone.strip() else None

        if address is not None:
            customer.address = address.strip() if address.strip() else None

        await self.user_repo.session.flush()
        return user, customer

    async def assign_store_manager(
        self,
        admin_user: User,
        target_user_id: UUID,
        store_id: UUID,
    ) -> User:
        """
        Assign a user as STORE_MANAGER for a designated store.
        Strictly restricted to ADMIN or SUPER_ADMIN callers.
        Validates store exists and is active.
        Enforces PostgreSQL check constraint by setting role and store_id together.
        """
        if admin_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
            raise ForbiddenError("Only administrators can assign store managers")

        if self.store_repo is not None:
            store = await self.store_repo.get_by_id(store_id)
            if store is None:
                raise NotFoundError(f"Store with id '{store_id}' not found")
            if not store.is_active:
                raise BadRequestError(
                    f"Cannot assign manager to inactive store '{store.name}' ({store.code})"
                )

        target_user = await self.get_user_by_id(target_user_id)
        target_user.role = UserRole.STORE_MANAGER
        target_user.assigned_store_id = store_id

        await self.user_repo.session.flush()
        return target_user

    async def update_user_status(
        self,
        admin_user: User,
        target_user_id: UUID,
        is_active: bool,
    ) -> User:
        """
        Activate or deactivate a user account.
        Strictly restricted to ADMIN or SUPER_ADMIN callers.
        Prevents administrators from deactivating their own account.
        """
        if admin_user.role not in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
            raise ForbiddenError("Only administrators can modify user status")

        if target_user_id == admin_user.id and not is_active:
            raise BadRequestError("Administrators cannot deactivate their own account")

        target_user = await self.get_user_by_id(target_user_id)
        target_user.is_active = is_active

        await self.user_repo.session.flush()
        return target_user
