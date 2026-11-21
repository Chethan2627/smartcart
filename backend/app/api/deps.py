"""
Reusable dependencies and dependency factories for SmartCart 2.0 FastAPI application.
Provides:
- Database session lifecycle management.
- Repository and domain service factory dependencies.
- Cryptographic JWT bearer authentication and user resolution.
- Strict role-based authorization (CUSTOMER, STORE_MANAGER, ADMIN, SUPER_ADMIN).
- Store-manager store scoping and isolation.
- Customer resource ownership validation.
- Idempotency-Key header extraction and validation.
"""
from datetime import datetime, timezone
import re
from typing import Any, AsyncGenerator, Dict, List, Optional, Set
from uuid import UUID

from fastapi import Depends, Header, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    AuthenticationError,
    BadRequestError,
    ForbiddenError,
    InvalidTokenError,
    NotFoundError,
    ValidationError,
)
from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.customer import Customer
from app.models.enums import UserRole
from app.models.user import User
from app.repositories import (
    CustomerRepository,
    IdempotencyKeyRepository,
    InventoryAuditLogRepository,
    InventoryRepository,
    OrderRepository,
    OutboxEventRepository,
    ProcessedEventRepository,
    ProductRepository,
    ReservationRepository,
    StoreRepository,
    UserRepository,
)
from app.services.auth import AuthService
from app.services.cart import CartService
from app.services.checkout import CheckoutService
from app.services.idempotency import IdempotencyService
from app.services.inventory import InventoryService
from app.services.order import OrderService
from app.services.outbox import OutboxService
from app.services.product import ProductService
from app.services.storage import CloudinaryStorageService, ImageStorageService
from app.services.store import StoreService
from app.services.store_manager import StoreManagerService
from app.services.user import UserService

# Bearer token extractor (auto_error=False ensures missing tokens raise domain AuthenticationError)
security_scheme = HTTPBearer(auto_error=False)

IDEMPOTENCY_KEY_REGEX = re.compile(r"^[A-Za-z0-9_-]{1,255}$")


# ============================================================================
# 1. Repository Dependencies
# ============================================================================

def get_user_repository(session: AsyncSession = Depends(get_db)) -> UserRepository:
    return UserRepository(session)


def get_customer_repository(session: AsyncSession = Depends(get_db)) -> CustomerRepository:
    return CustomerRepository(session)


def get_store_repository(session: AsyncSession = Depends(get_db)) -> StoreRepository:
    return StoreRepository(session)


def get_product_repository(session: AsyncSession = Depends(get_db)) -> ProductRepository:
    return ProductRepository(session)


def get_inventory_repository(session: AsyncSession = Depends(get_db)) -> InventoryRepository:
    return InventoryRepository(session)


def get_reservation_repository(session: AsyncSession = Depends(get_db)) -> ReservationRepository:
    return ReservationRepository(session)


def get_order_repository(session: AsyncSession = Depends(get_db)) -> OrderRepository:
    return OrderRepository(session)


def get_idempotency_repository(session: AsyncSession = Depends(get_db)) -> IdempotencyKeyRepository:
    return IdempotencyKeyRepository(session)


def get_outbox_repository(session: AsyncSession = Depends(get_db)) -> OutboxEventRepository:
    return OutboxEventRepository(session)


def get_processed_event_repository(session: AsyncSession = Depends(get_db)) -> ProcessedEventRepository:
    return ProcessedEventRepository(session)


def get_inventory_audit_repository(session: AsyncSession = Depends(get_db)) -> InventoryAuditLogRepository:
    return InventoryAuditLogRepository(session)


# ============================================================================
# 2. Domain Service Factory Dependencies
# ============================================================================

def get_auth_service(session: AsyncSession = Depends(get_db)) -> AuthService:
    return AuthService(
        user_repo=UserRepository(session),
        customer_repo=CustomerRepository(session),
    )


def get_user_service(session: AsyncSession = Depends(get_db)) -> UserService:
    return UserService(
        user_repo=UserRepository(session),
        customer_repo=CustomerRepository(session),
        store_repo=StoreRepository(session),
    )


def get_store_service(session: AsyncSession = Depends(get_db)) -> StoreService:
    return StoreService(
        store_repo=StoreRepository(session),
        user_repo=UserRepository(session),
    )


def get_product_service(session: AsyncSession = Depends(get_db)) -> ProductService:
    return ProductService(
        product_repo=ProductRepository(session),
    )


def get_inventory_service(session: AsyncSession = Depends(get_db)) -> InventoryService:
    return InventoryService(
        inventory_repo=InventoryRepository(session),
        reservation_repo=ReservationRepository(session),
        session=session,
    )


def get_cart_service(session: AsyncSession = Depends(get_db)) -> CartService:
    inv_service = InventoryService(
        InventoryRepository(session),
        ReservationRepository(session),
        session=session,
    )
    prod_service = ProductService(ProductRepository(session))
    store_service = StoreService(StoreRepository(session), UserRepository(session))
    return CartService(
        inventory_service=inv_service,
        product_service=prod_service,
        store_service=store_service,
        reservation_repo=ReservationRepository(session),
        session=session,
    )


def get_order_service(session: AsyncSession = Depends(get_db)) -> OrderService:
    return OrderService(
        order_repo=OrderRepository(session),
        session=session,
    )


def get_idempotency_service(session: AsyncSession = Depends(get_db)) -> IdempotencyService:
    return IdempotencyService(
        idempotency_repo=IdempotencyKeyRepository(session),
        session=session,
    )


def get_outbox_service(session: AsyncSession = Depends(get_db)) -> OutboxService:
    return OutboxService(
        outbox_repo=OutboxEventRepository(session),
        processed_repo=ProcessedEventRepository(session),
        session=session,
    )


def get_checkout_service(session: AsyncSession = Depends(get_db)) -> CheckoutService:
    order_repo = OrderRepository(session)
    inv_service = InventoryService(
        InventoryRepository(session),
        ReservationRepository(session),
        session=session,
    )
    prod_service = ProductService(ProductRepository(session))
    store_service = StoreService(StoreRepository(session), UserRepository(session))
    cart_service = CartService(
        inventory_service=inv_service,
        product_service=prod_service,
        store_service=store_service,
        reservation_repo=ReservationRepository(session),
        session=session,
    )
    idemp_service = IdempotencyService(
        IdempotencyKeyRepository(session),
        session=session,
    )
    return CheckoutService(
        order_repo=order_repo,
        cart_service=cart_service,
        product_service=prod_service,
        store_service=store_service,
        idempotency_service=idemp_service,
        session=session,
    )


def get_storage_service() -> ImageStorageService:
    return CloudinaryStorageService()


def get_store_manager_service(
    session: AsyncSession = Depends(get_db),
    storage_service: ImageStorageService = Depends(get_storage_service),
) -> StoreManagerService:
    return StoreManagerService(
        product_repo=ProductRepository(session),
        inventory_repo=InventoryRepository(session),
        audit_repo=InventoryAuditLogRepository(session),
        outbox_service=OutboxService(
            outbox_repo=OutboxEventRepository(session),
            processed_repo=ProcessedEventRepository(session),
            session=session,
        ),
        storage_service=storage_service,
        session=session,
    )


def get_product_index_service() -> Any:
    from app.opensearch.indexing import ProductIndexService
    return ProductIndexService()


def get_product_search_service() -> Any:
    from app.opensearch.search import ProductSearchService
    return ProductSearchService()


# ============================================================================
# 3. Authentication & Current User Dependencies
# ============================================================================

async def get_token_payload(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
) -> Dict[str, Any]:
    """
    Extract and verify JWT access token from Authorization: Bearer <token> header.
    Raises AuthenticationError if header is missing.
    Raises TokenExpiredError or InvalidTokenError if token is expired or tampered.
    """
    if credentials is None or not credentials.credentials or not credentials.credentials.strip():
        raise AuthenticationError("Authentication token is required")

    return decode_access_token(credentials.credentials)


async def get_current_user(
    payload: Dict[str, Any] = Depends(get_token_payload),
    session: AsyncSession = Depends(get_db),
) -> User:
    """
    Resolve authenticated User entity from PostgreSQL using token's subject claim.
    Validates user existence and rejects inactive user accounts.
    Never trusts client-supplied role or store claims.
    """
    sub = payload.get("sub")
    if not sub:
        raise InvalidTokenError("Access token payload missing valid subject ('sub') claim")

    try:
        user_id = UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise InvalidTokenError(f"Access token subject '{sub}' is not a valid UUID") from exc

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise AuthenticationError("Authenticated user does not exist")

    if not user.is_active:
        raise ForbiddenError("User account is inactive. Please contact support.")

    return user


async def get_optional_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_scheme),
    session: AsyncSession = Depends(get_db),
) -> Optional[User]:
    """
    Resolve authenticated User if Authorization header is present; otherwise return None.
    If credentials are provided:
    - Raises TokenExpiredError or InvalidTokenError if the token is invalid or expired.
    - Raises AuthenticationError if the user does not exist.
    - Raises ForbiddenError if the user account is inactive.
    - Returns the active User entity if valid.
    """
    if credentials is None or not credentials.credentials or not credentials.credentials.strip():
        return None

    payload = decode_access_token(credentials.credentials)
    sub = payload.get("sub")
    if not sub:
        raise InvalidTokenError("Access token payload missing valid subject ('sub') claim")

    try:
        user_id = UUID(str(sub))
    except (ValueError, TypeError) as exc:
        raise InvalidTokenError(f"Access token subject '{sub}' is not a valid UUID") from exc

    user_repo = UserRepository(session)
    user = await user_repo.get_by_id(user_id)
    if user is None:
        raise AuthenticationError("Authenticated user does not exist")

    if not user.is_active:
        raise ForbiddenError("User account is inactive. Please contact support.")

    return user


async def get_current_active_user(user: User = Depends(get_current_user)) -> User:
    """Dependency returning active authenticated user."""
    return user



async def get_current_customer(
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> Customer:
    """
    Resolve Customer profile corresponding to authenticated User.
    Ensures user possesses the CUSTOMER role and has an associated customer record.
    """
    if user.role != UserRole.CUSTOMER:
        raise ForbiddenError(f"User role '{user.role.value}' is not authorized for customer operations")

    cust_repo = CustomerRepository(session)
    customer = await cust_repo.get_by_user_id(user.id)
    if customer is None:
        raise NotFoundError("Customer profile not found for authenticated user")

    return customer


# ============================================================================
# 4. Role-Based Authorization Dependencies
# ============================================================================

class RoleChecker:
    """
    Dependency callable that validates the authenticated user's authoritative role.
    Raises ForbiddenError (HTTP 403) if the user's role is not in allowed roles.
    """

    def __init__(self, *allowed_roles: UserRole) -> None:
        self.allowed_roles: Set[UserRole] = set(allowed_roles)

    async def __call__(self, current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in self.allowed_roles:
            raise ForbiddenError(
                f"User role '{current_user.role.value}' is not authorized to access this resource"
            )
        return current_user


def require_roles(*roles: UserRole) -> RoleChecker:
    """Factory creating a role-checking dependency for arbitrary roles."""
    return RoleChecker(*roles)


# Pre-configured role dependencies
require_customer = RoleChecker(UserRole.CUSTOMER)
require_store_manager = RoleChecker(UserRole.STORE_MANAGER)
require_admin = RoleChecker(UserRole.ADMIN, UserRole.SUPER_ADMIN)
require_super_admin = RoleChecker(UserRole.SUPER_ADMIN)
require_staff = RoleChecker(UserRole.STORE_MANAGER, UserRole.ADMIN, UserRole.SUPER_ADMIN)


# ============================================================================
# 5. Store Manager & Customer Ownership Authorization
# ============================================================================

def verify_store_manager_access(user: User, store_id: UUID) -> None:
    """
    Enforce store isolation:
    - STORE_MANAGER can ONLY access their assigned store.
    - ADMIN and SUPER_ADMIN have multi-store access across all stores.
    - All other roles are rejected with ForbiddenError.
    """
    if user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        return

    if user.role == UserRole.STORE_MANAGER:
        if user.assigned_store_id is None or user.assigned_store_id != store_id:
            raise ForbiddenError(
                f"Store manager is not authorized to manage store '{store_id}'"
            )
        return

    raise ForbiddenError(
        f"User role '{user.role.value}' is not authorized to manage store resources"
    )


class RequireStoreAccess:
    """
    FastAPI dependency validating that the current user has authority to manage
    the store identified by the route's store_id path parameter.
    """

    async def __call__(
        self,
        store_id: UUID,
        current_user: User = Depends(get_current_user),
    ) -> User:
        verify_store_manager_access(current_user, store_id)
        return current_user


require_store_access = RequireStoreAccess()


async def resolve_manager_store_id(
    store_id: Optional[UUID] = Query(default=None, description="Target store ID"),
    current_user: User = Depends(get_current_user),
) -> UUID:
    """
    Resolve authoritative store_id for store management routes:
    - STORE_MANAGER: must manage user.assigned_store_id; rejects cross-store requests.
    - ADMIN / SUPER_ADMIN: can manage any store specified via store_id query param.
    """
    if current_user.role == UserRole.STORE_MANAGER:
        if current_user.assigned_store_id is None:
            raise ForbiddenError("Store manager account is not assigned to any store")
        if store_id is not None and store_id != current_user.assigned_store_id:
            raise ForbiddenError(f"Store manager is not authorized to manage store '{store_id}'")
        return current_user.assigned_store_id
    elif current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        if store_id is None:
            raise BadRequestError("store_id parameter is required for administrator requests")
        return store_id

    raise ForbiddenError(
        f"User role '{current_user.role.value}' is not authorized for store management operations"
    )


def verify_customer_ownership(
    current_user: User,
    target_customer_id: UUID,
    current_customer: Optional[Customer] = None,
) -> None:
    """
    Enforce customer ownership:
    - CUSTOMER can ONLY access resources belonging to their own customer ID.
    - ADMIN and SUPER_ADMIN can inspect any customer's resources.
    - All other roles are rejected with ForbiddenError.
    """
    if current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
        return

    if current_user.role == UserRole.CUSTOMER:
        if current_customer is not None and current_customer.id != target_customer_id:
            raise ForbiddenError("Access to another customer's resource is forbidden")
        return

    raise ForbiddenError(
        f"User role '{current_user.role.value}' is not authorized to access customer resources"
    )


class RequireCustomerOwnership:
    """
    FastAPI dependency validating that the resource customer_id matches
    the authenticated customer, or that caller has administrative privileges.
    """

    async def __call__(
        self,
        customer_id: UUID,
        current_user: User = Depends(get_current_user),
        session: AsyncSession = Depends(get_db),
    ) -> Customer:
        if current_user.role in (UserRole.ADMIN, UserRole.SUPER_ADMIN):
            cust_repo = CustomerRepository(session)
            target_cust = await cust_repo.get_by_id(customer_id)
            if target_cust is None:
                raise NotFoundError(f"Customer '{customer_id}' not found")
            return target_cust

        if current_user.role == UserRole.CUSTOMER:
            cust_repo = CustomerRepository(session)
            current_cust = await cust_repo.get_by_user_id(current_user.id)
            if current_cust is None or current_cust.id != customer_id:
                raise ForbiddenError("Access to another customer's resource is forbidden")
            return current_cust

        raise ForbiddenError(
            f"User role '{current_user.role.value}' is not authorized to access customer resources"
        )


require_customer_ownership = RequireCustomerOwnership()


# ============================================================================
# 6. Idempotency Header Dependency
# ============================================================================

def get_idempotency_key(
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> Optional[str]:
    """
    Extract and validate client-supplied Idempotency-Key HTTP header.
    Validates regex [A-Za-z0-9_-]{1,255}.
    Returns None if header is not present.
    """
    if idempotency_key is not None:
        trimmed = idempotency_key.strip()
        if not trimmed or not IDEMPOTENCY_KEY_REGEX.match(trimmed):
            raise ValidationError(
                "Idempotency-Key header must be 1-255 characters consisting only of alphanumeric, underscore, or hyphen"
            )
        return trimmed
    return None


def require_idempotency_key(
    idempotency_key: Optional[str] = Header(None, alias="Idempotency-Key"),
) -> str:
    """
    Extract and validate required client-supplied Idempotency-Key HTTP header.
    Strictly requires non-empty header matching regex [A-Za-z0-9_-]{1,255}.
    Raises ValidationError if missing or invalid.
    """
    if idempotency_key is None:
        raise ValidationError("Idempotency-Key request header is required for checkout")

    trimmed = idempotency_key.strip()
    if not trimmed or not IDEMPOTENCY_KEY_REGEX.match(trimmed):
        raise ValidationError(
            "Idempotency-Key header must be 1-255 characters consisting only of alphanumeric, underscore, or hyphen"
        )
    return trimmed


__all__ = [
    # DB
    "get_db",
    # Repositories
    "get_user_repository",
    "get_customer_repository",
    "get_store_repository",
    "get_product_repository",
    "get_inventory_repository",
    "get_reservation_repository",
    "get_order_repository",
    "get_idempotency_repository",
    "get_outbox_repository",
    "get_processed_event_repository",
    "get_inventory_audit_repository",
    # Services
    "get_auth_service",
    "get_user_service",
    "get_store_service",
    "get_product_service",
    "get_inventory_service",
    "get_cart_service",
    "get_order_service",
    "get_checkout_service",
    "get_idempotency_service",
    "get_outbox_service",
    "get_storage_service",
    "get_store_manager_service",
    "get_product_index_service",
    "get_product_search_service",
    # Auth & Current User
    "security_scheme",
    "get_token_payload",
    "get_current_user",
    "get_optional_current_user",
    "get_current_active_user",
    "get_current_customer",
    # Role Authorization
    "RoleChecker",
    "require_roles",
    "require_customer",
    "require_store_manager",
    "require_admin",
    "require_super_admin",
    "require_staff",
    # Store Manager & Customer Ownership
    "verify_store_manager_access",
    "require_store_access",
    "resolve_manager_store_id",
    "verify_customer_ownership",
    "require_customer_ownership",
    # Idempotency
    "get_idempotency_key",
    "require_idempotency_key",
]
