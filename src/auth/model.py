from sqlalchemy import String, Boolean, DateTime, Integer
from src.core.model import ORMBase
from sqlalchemy.orm import mapped_column, Mapped


class Guest(ORMBase):
    __tablename__ = "guests"
    name = mapped_column(String, nullable=False)
    code: Mapped[int] = mapped_column(Integer, nullable=False)
    event_name = mapped_column(String, nullable=False)
    event_id = mapped_column(String, nullable=False)
    checked_in = mapped_column(Boolean, default=False)
    is_active = mapped_column(Boolean, default=True)


class Host(ORMBase):
    __tablename__ = "hosts"
    email: Mapped[str] = mapped_column(
        String(255), unique=True, nullable=False, index=True
    )
    first_name = mapped_column(String(255), nullable=True)
    last_name = mapped_column(String(255), nullable=True)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    is_active = mapped_column(Boolean, default=False)


class Job(ORMBase):
    __tablename__ = "jobs"
    status: Mapped[str] = mapped_column(String(255), nullable=False)
    result: Mapped[str] = mapped_column(String(255), nullable=True)
    error: Mapped[str] = mapped_column(String(255), nullable=True)
