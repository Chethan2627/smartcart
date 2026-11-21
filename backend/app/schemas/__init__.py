from app.schemas.auth import LoginRequest, TokenPayload, TokenResponse
from app.schemas.common import EmailStr, ErrorDetail, ErrorResponse, PaginationParams
from app.schemas.cart import (
    CartItemAddRequest,
    CartItemResponse,
    CartItemUpdateRequest,
    CartResponse,
)

from app.schemas.idempotency import IdempotencyKeyHeader, IdempotencyRecordResponse
from app.schemas.outbox import (
    OutboxEventDetailResponse,
    OutboxEventResponse,
    OutboxEventSummaryResponse,
)

from app.schemas.inventory import (
    InventoryAuditLogResponse,
    ReservationCreateRequest,
    ReservationResponse,
    StockResponse,
)
from app.schemas.order import (
    CheckoutRequest,
    OrderCancelRequest,
    OrderFilterParams,
    OrderItemResponse,
    OrderResponse,
    OrderStatusHistoryResponse,
    OrderStatusUpdateRequest,
)
from app.schemas.product import ProductFilterParams, ProductResponse
from app.schemas.store import StoreFilterParams, StoreResponse
from app.schemas.user import (
    CustomerProfileResponse,
    CustomerRegisterRequest,
    StoreManagerAssignRequest,
    UserResponse,
    UserStatusUpdateRequest,
)

__all__ = [
    # Common
    "EmailStr",
    "PaginationParams",
    "ErrorDetail",
    "ErrorResponse",
    # Auth
    "LoginRequest",
    "TokenResponse",
    "TokenPayload",
    # User
    "CustomerRegisterRequest",
    "UserResponse",
    "CustomerProfileResponse",
    "StoreManagerAssignRequest",
    "UserStatusUpdateRequest",
    # Store
    "StoreResponse",
    "StoreFilterParams",
    # Product
    "ProductResponse",
    "ProductFilterParams",
    # Inventory
    "StockResponse",
    "ReservationCreateRequest",
    "ReservationResponse",
    "InventoryAuditLogResponse",
    # Cart
    "CartItemAddRequest",
    "CartItemUpdateRequest",
    "CartItemResponse",
    "CartResponse",
    # Order
    "CheckoutRequest",
    "OrderItemResponse",
    "OrderStatusHistoryResponse",
    "OrderResponse",
    "OrderCancelRequest",
    "OrderStatusUpdateRequest",
    "OrderFilterParams",
    # Idempotency
    "IdempotencyKeyHeader",
    "IdempotencyRecordResponse",
    # Outbox
    "OutboxEventSummaryResponse",
    "OutboxEventDetailResponse",
    "OutboxEventResponse",
]
