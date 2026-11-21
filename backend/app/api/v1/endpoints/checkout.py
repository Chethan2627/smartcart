"""
SmartCart 2.0 – Checkout Orchestration API Endpoints.
Provides:
- Atomic checkout and order placement (POST /api/v1/checkout).

Guarantees:
- Strictly requires and validates the Idempotency-Key HTTP header.
- Replays cached responses safely on identical duplicate submissions without double-charging or re-ordering.
- Detects key reuse with modified payloads and returns HTTP 409 Conflict.
- Customer ID derived exclusively from verified JWT authentication.
- Prices and totals are computed exclusively server-side from PostgreSQL authoritative product records in paise.
- Delegates atomic reservation consumption, order confirmation, and outbox event creation to CheckoutService.
- Route never calls session.commit() directly, preserving CheckoutService's transaction ownership.
"""
from fastapi import APIRouter, Depends, status

from app.api.deps import (
    get_checkout_service,
    get_current_customer,
    require_idempotency_key,
)
from app.models.customer import Customer
from app.schemas.order import CheckoutRequest, OrderResponse
from app.services.checkout import CheckoutService

router = APIRouter(prefix="/checkout", tags=["Checkout"])


@router.post(
    "",
    response_model=OrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Initiate atomic checkout and confirm order",
    description=(
        "Converts active cart reservations into a confirmed order. "
        "Strictly requires the Idempotency-Key header. Automatically links held reservations, "
        "decrements store inventory, transitions order to CONFIRMED, and enqueues transactional "
        "outbox events in a single atomic database transaction. Replays identical requests safely."
    ),
)
async def checkout(
    payload: CheckoutRequest,
    current_customer: Customer = Depends(get_current_customer),
    idempotency_key: str = Depends(require_idempotency_key),
    checkout_service: CheckoutService = Depends(get_checkout_service),
) -> OrderResponse:
    """
    Perform atomic checkout and order confirmation.
    Transaction management is owned entirely by CheckoutService.
    """
    return await checkout_service.checkout(
        customer_id=current_customer.id,
        request=payload,
        idempotency_key=idempotency_key,
    )
