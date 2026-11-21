import pytest
from sqlalchemy import BigInteger, DateTime, inspect
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import configure_mappers

from app.db.base import Base
import app.models as models
from app.models.enums import (
    OrderStatus,
    OutboxStatus,
    ReservationStatus,
    UserRole,
    order_status_enum,
    outbox_status_enum,
    reservation_status_enum,
    user_role_enum,
)


def test_all_13_tables_registered():
    """Verify that all 13 PostgreSQL tables from 01_schema.sql are registered in Base.metadata."""
    expected_tables = {
        "stores",
        "users",
        "customers",
        "products",
        "orders",
        "order_items",
        "order_status_history",
        "inventory",
        "reservations",
        "idempotency_keys",
        "inventory_audit_log",
        "outbox_events",
        "processed_events",
    }
    registered_tables = set(Base.metadata.tables.keys())
    assert registered_tables == expected_tables, f"Mismatch: {expected_tables ^ registered_tables}"


def test_primary_keys_and_composite_pks():
    """Verify primary keys for all models, with specific emphasis on composite primary keys."""
    # Single PK tables
    single_pks = {
        "stores": ["id"],
        "users": ["id"],
        "customers": ["id"],
        "products": ["id"],
        "orders": ["id"],
        "order_items": ["id"],
        "order_status_history": ["id"],
        "reservations": ["id"],
        "inventory_audit_log": ["id"],
        "outbox_events": ["id"],
    }
    for table_name, expected_cols in single_pks.items():
        table = Base.metadata.tables[table_name]
        pk_cols = [c.name for c in table.primary_key.columns]
        assert pk_cols == expected_cols, f"{table_name} PK mismatch: expected {expected_cols}, got {pk_cols}"

    # Composite PK tables
    composite_pks = {
        "inventory": ["store_id", "product_id"],
        "processed_events": ["event_id", "consumer_group"],
        "idempotency_keys": ["customer_id", "key"],
    }
    for table_name, expected_cols in composite_pks.items():
        table = Base.metadata.tables[table_name]
        pk_cols = [c.name for c in table.primary_key.columns]
        assert pk_cols == expected_cols, f"{table_name} composite PK mismatch: expected {expected_cols}, got {pk_cols}"


def test_foreign_keys_and_composite_fks():
    """Verify foreign keys and composite foreign keys match 01_schema.sql."""
    # Customer user_id -> users.id ON DELETE CASCADE
    cust_table = Base.metadata.tables["customers"]
    cust_fk = list(cust_table.foreign_keys)[0]
    assert cust_fk.target_fullname == "users.id"
    assert cust_fk.ondelete == "CASCADE"

    # Order foreign keys
    orders_table = Base.metadata.tables["orders"]
    order_fks = {fk.target_fullname for fk in orders_table.foreign_keys}
    assert "customers.id" in order_fks
    assert "stores.id" in order_fks

    # OrderItem foreign keys
    items_table = Base.metadata.tables["order_items"]
    item_fks = {fk.target_fullname: fk.ondelete for fk in items_table.foreign_keys}
    assert item_fks["orders.id"] == "CASCADE"
    assert "products.id" in item_fks

    # OrderStatusHistory foreign keys
    history_table = Base.metadata.tables["order_status_history"]
    history_fk = list(history_table.foreign_keys)[0]
    assert history_fk.target_fullname == "orders.id"
    assert history_fk.ondelete == "CASCADE"

    # Inventory foreign keys
    inv_table = Base.metadata.tables["inventory"]
    inv_fks = {fk.target_fullname for fk in inv_table.foreign_keys}
    assert "stores.id" in inv_fks
    assert "products.id" in inv_fks

    # Reservation composite foreign key to inventory(store_id, product_id)
    res_table = Base.metadata.tables["reservations"]
    res_fk_targets = {fk.target_fullname for fk in res_table.foreign_keys}
    assert "customers.id" in res_fk_targets
    assert "orders.id" in res_fk_targets
    assert "inventory.store_id" in res_fk_targets
    assert "inventory.product_id" in res_fk_targets

    # IdempotencyKey foreign keys
    idem_table = Base.metadata.tables["idempotency_keys"]
    idem_fks = {fk.target_fullname for fk in idem_table.foreign_keys}
    assert "customers.id" in idem_fks
    assert "orders.id" in idem_fks

    # InventoryAuditLog must have NO foreign keys (matching 01_schema.sql)
    audit_table = Base.metadata.tables["inventory_audit_log"]
    assert len(audit_table.foreign_keys) == 0, "InventoryAuditLog must NOT have foreign keys"


def test_postgresql_enum_mappings():
    """Verify PostgreSQL ENUM mappings match 01_schema.sql enums exactly."""
    enum_expectations = [
        (UserRole, user_role_enum, "user_role", ["CUSTOMER", "STORE_MANAGER", "ADMIN", "SUPER_ADMIN"]),
        (OrderStatus, order_status_enum, "order_status", ["PENDING", "CONFIRMED", "PACKED", "SHIPPED", "DELIVERED", "CANCELLED"]),
        (ReservationStatus, reservation_status_enum, "reservation_status", ["ACTIVE", "CONSUMED", "RELEASED", "EXPIRED"]),
        (OutboxStatus, outbox_status_enum, "outbox_status", ["PENDING", "PUBLISHED", "FAILED"]),
    ]

    for enum_cls, pg_enum, expected_name, expected_values in enum_expectations:
        assert pg_enum.name == expected_name
        assert pg_enum.create_type is False
        assert callable(pg_enum.values_callable)
        values = pg_enum.values_callable(enum_cls)
        assert values == expected_values, f"Enum {expected_name} values mismatch: {values} vs {expected_values}"


def test_column_types_uuid_bigint_jsonb_timestamptz():
    """Verify column types: UUID, BigInteger, JSONB, and TIMESTAMPTZ."""
    tables = Base.metadata.tables

    # UUID columns
    uuid_cols = [
        ("stores", "id"),
        ("users", "id"),
        ("customers", "id"),
        ("products", "id"),
        ("orders", "id"),
        ("reservations", "id"),
        ("outbox_events", "id"),
        ("inventory_audit_log", "store_id"),
        ("inventory_audit_log", "product_id"),
    ]
    for tbl_name, col_name in uuid_cols:
        col = tables[tbl_name].columns[col_name]
        assert isinstance(col.type, UUID), f"{tbl_name}.{col_name} should be UUID, got {type(col.type)}"

    # BigInteger columns
    bigint_cols = [
        ("products", "price_paise"),
        ("orders", "total_paise"),
        ("order_items", "unit_price_paise"),
        ("order_items", "id"),
        ("order_status_history", "id"),
        ("inventory_audit_log", "id"),
    ]
    for tbl_name, col_name in bigint_cols:
        col = tables[tbl_name].columns[col_name]
        assert isinstance(col.type, BigInteger), f"{tbl_name}.{col_name} should be BigInteger, got {type(col.type)}"

    # JSONB columns
    jsonb_cols = [
        ("products", "attributes"),
        ("outbox_events", "payload"),
        ("idempotency_keys", "response"),
    ]
    for tbl_name, col_name in jsonb_cols:
        col = tables[tbl_name].columns[col_name]
        assert isinstance(col.type, JSONB), f"{tbl_name}.{col_name} should be JSONB, got {type(col.type)}"

    # Timezone-aware timestamp columns
    timestamptz_cols = [
        ("stores", "created_at"),
        ("users", "created_at"),
        ("users", "updated_at"),
        ("customers", "created_at"),
        ("products", "created_at"),
        ("products", "updated_at"),
        ("orders", "created_at"),
        ("orders", "updated_at"),
        ("order_status_history", "changed_at"),
        ("inventory", "updated_at"),
        ("reservations", "expires_at"),
        ("reservations", "created_at"),
        ("reservations", "updated_at"),
        ("idempotency_keys", "created_at"),
        ("inventory_audit_log", "changed_at"),
        ("outbox_events", "created_at"),
        ("outbox_events", "published_at"),
        ("processed_events", "processed_at"),
    ]
    for tbl_name, col_name in timestamptz_cols:
        col = tables[tbl_name].columns[col_name]
        assert isinstance(col.type, DateTime), f"{tbl_name}.{col_name} should be DateTime, got {type(col.type)}"
        assert col.type.timezone is True, f"{tbl_name}.{col_name} DateTime must have timezone=True"


def test_partial_indexes_and_gin():
    """Verify partial indexes and GIN index with exact WHERE clauses."""
    tables = Base.metadata.tables

    # GIN index on products.attributes
    prod_table = tables["products"]
    prod_gin = next(idx for idx in prod_table.indexes if idx.name == "products_attributes_gin")
    assert prod_gin.dialect_options["postgresql"]["using"] == "gin"

    # Partial index on users (assigned_store_id) WHERE assigned_store_id IS NOT NULL
    users_table = tables["users"]
    user_part_idx = next(idx for idx in users_table.indexes if idx.name == "users_assigned_store_idx")
    assert "assigned_store_id IS NOT NULL" in str(user_part_idx.dialect_options["postgresql"]["where"])

    # Partial index on reservations (expires_at) WHERE status = 'ACTIVE'
    res_table = tables["reservations"]
    res_active_idx = next(idx for idx in res_table.indexes if idx.name == "reservations_active_expiry_idx")
    assert "status = 'ACTIVE'" in str(res_active_idx.dialect_options["postgresql"]["where"])

    # Partial index on reservations (order_id) WHERE order_id IS NOT NULL
    res_order_idx = next(idx for idx in res_table.indexes if idx.name == "reservations_order_idx")
    assert "order_id IS NOT NULL" in str(res_order_idx.dialect_options["postgresql"]["where"])

    # Partial index on outbox_events (created_at) WHERE status = 'PENDING'
    outbox_table = tables["outbox_events"]
    outbox_pending_idx = next(idx for idx in outbox_table.indexes if idx.name == "outbox_events_pending_idx")
    assert "status = 'PENDING'" in str(outbox_pending_idx.dialect_options["postgresql"]["where"])


def test_check_constraints_and_unique_constraints():
    """Verify key check constraints and unique constraints."""
    tables = Base.metadata.tables

    # User role check constraint
    user_checks = {c.name: str(c.sqltext) for c in tables["users"].constraints if hasattr(c, "sqltext")}
    assert "check_store_manager_assignment" in user_checks

    # Product price check constraint
    prod_checks = {c.name: str(c.sqltext) for c in tables["products"].constraints if hasattr(c, "sqltext")}
    assert "products_price_paise_check" in prod_checks

    # Order total check constraint
    order_checks = {c.name: str(c.sqltext) for c in tables["orders"].constraints if hasattr(c, "sqltext")}
    assert "orders_total_paise_check" in order_checks

    # OrderItem unique constraint
    item_uniqs = {c.name: [col.name for col in c.columns] for c in tables["order_items"].constraints if hasattr(c, "columns") and not hasattr(c, "sqltext") and c.name == "order_items_order_product_uniq"}
    assert "order_items_order_product_uniq" in item_uniqs
    assert item_uniqs["order_items_order_product_uniq"] == ["order_id", "product_id"]

    # Inventory checks
    inv_checks = {c.name: str(c.sqltext) for c in tables["inventory"].constraints if hasattr(c, "sqltext")}
    assert "inventory_check" in inv_checks
    assert "inventory_qty_on_hand_check" in inv_checks
    assert "inventory_qty_reserved_check" in inv_checks


def test_relationship_mapper_configuration_and_bidirectional():
    """Verify configure_mappers() succeeds and all bi-directional relationships are valid."""
    # This raises if any mapper or relationship is misconfigured
    configure_mappers()

    # Store relationships
    store_mapper = inspect(models.Store)
    assert "assigned_managers" in store_mapper.relationships
    assert "inventory" in store_mapper.relationships
    assert "orders" in store_mapper.relationships

    # User relationships
    user_mapper = inspect(models.User)
    assert "assigned_store" in user_mapper.relationships
    assert "customer_profile" in user_mapper.relationships

    # Customer relationships
    cust_mapper = inspect(models.Customer)
    assert "user" in cust_mapper.relationships
    assert "orders" in cust_mapper.relationships
    assert "reservations" in cust_mapper.relationships
    assert "idempotency_keys" in cust_mapper.relationships

    # Product relationships
    prod_mapper = inspect(models.Product)
    assert "inventory_items" in prod_mapper.relationships
    assert "order_items" in prod_mapper.relationships

    # Order relationships
    order_mapper = inspect(models.Order)
    assert "customer" in order_mapper.relationships
    assert "store" in order_mapper.relationships
    assert "items" in order_mapper.relationships
    assert "status_history" in order_mapper.relationships
    assert "reservations" in order_mapper.relationships
    assert "idempotency_keys" in order_mapper.relationships

    # Inventory relationships
    inv_mapper = inspect(models.Inventory)
    assert "store" in inv_mapper.relationships
    assert "product" in inv_mapper.relationships
    assert "reservations" in inv_mapper.relationships

    # Reservation relationships
    res_mapper = inspect(models.Reservation)
    assert "customer" in res_mapper.relationships
    assert "order" in res_mapper.relationships
    assert "inventory" in res_mapper.relationships

    # IdempotencyKey relationships
    idem_mapper = inspect(models.IdempotencyKey)
    assert "customer" in idem_mapper.relationships
    assert "order" in idem_mapper.relationships


def test_cascade_safety_and_passive_deletes():
    """Verify that ORM does not introduce unintended client-side delete cascades."""
    order_mapper = inspect(models.Order)
    items_rel = order_mapper.relationships["items"]
    history_rel = order_mapper.relationships["status_history"]

    # Since the DB tables have ON DELETE CASCADE, passive_deletes must be True
    # so SQLAlchemy allows PostgreSQL to handle the cascade efficiently
    assert items_rel.passive_deletes is True
    assert history_rel.passive_deletes is True

    # Customer.user relationship passive_deletes
    user_mapper = inspect(models.User)
    cust_rel = user_mapper.relationships["customer_profile"]
    assert cust_rel.passive_deletes is True
