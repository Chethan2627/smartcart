from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """
    SQLAlchemy 2.0 declarative base class for all SmartCart ORM models.
    Provides metadata registry for Alembic migrations.
    """
    pass
