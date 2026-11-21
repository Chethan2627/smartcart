"""
API package for SmartCart 2.0.
"""
from app.api.v1.api import api_router
from app.api.deps import (
    get_db,
    get_current_user,
    get_current_active_user,
    get_current_customer,
    require_roles,
    require_customer,
    require_store_manager,
    require_admin,
    require_super_admin,
    require_staff,
    require_store_access,
    require_customer_ownership,
)

__all__ = [
    "api_router",
    "get_db",
    "get_current_user",
    "get_current_active_user",
    "get_current_customer",
    "require_roles",
    "require_customer",
    "require_store_manager",
    "require_admin",
    "require_super_admin",
    "require_staff",
    "require_store_access",
    "require_customer_ownership",
]
