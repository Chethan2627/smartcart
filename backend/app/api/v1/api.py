"""
SmartCart 2.0 – Central API v1 Router Registration.
Aggregates all versioned sub-routers for authentication, stores, products, inventory,
shopping cart, orders, and checkout.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, status
from app.api.v1.endpoints.auth import router as auth_router
from app.api.v1.endpoints.cart import router as cart_router
from app.api.v1.endpoints.checkout import router as checkout_router
from app.api.v1.endpoints.inventory import router as inventory_router
from app.api.v1.endpoints.manager import router as manager_router
from app.api.v1.endpoints.orders import router as orders_router
from app.api.v1.endpoints.products import router as products_router
from app.api.v1.endpoints.search import router as search_router
from app.api.v1.endpoints.stores import router as stores_router
from app.api.v1.endpoints.users import router as users_router
from app.config import settings

api_router = APIRouter()


@api_router.get("/", status_code=status.HTTP_200_OK, tags=["API v1"])
async def api_v1_info():
    """Information endpoint confirming API v1 operational readiness."""
    return {
        "project": "SmartCart 2.0",
        "api_version": "v1",
        "environment": settings.ENVIRONMENT,
        "status": "online",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


# Domain Sub-Routers
api_router.include_router(auth_router)
api_router.include_router(users_router)
api_router.include_router(stores_router)
api_router.include_router(products_router)
api_router.include_router(inventory_router)
api_router.include_router(cart_router)
api_router.include_router(checkout_router)
api_router.include_router(orders_router)
api_router.include_router(manager_router)
api_router.include_router(search_router)

