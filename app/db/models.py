"""Application tables.

Deliberately NOT stored here: passwords, password hashes, session tokens, refresh
tokens. SuperTokens owns all credential material. We store only ``auth_user_id``
as the link, plus a display cache of name/email that SuperTokens remains the
source of truth for.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import (
    DateTime, ForeignKey, Index, String, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


class User(Base):
    """Application profile, keyed to a SuperTokens user."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # the ONLY link to SuperTokens. No credential material is mirrored.
    auth_user_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(320), index=True)   # display cache
    name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, server_default="true")
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now(), onupdate=_now)

    roles: Mapped[list["UserRole"]] = relationship(
        back_populates="user", cascade="all, delete-orphan", lazy="selectin")

    @property
    def role_names(self) -> list[str]:
        return sorted(ur.role.name for ur in self.roles)


class Role(Base):
    __tablename__ = "roles"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(String(255), nullable=True)

    users: Mapped[list["UserRole"]] = relationship(back_populates="role")


class UserRole(Base):
    __tablename__ = "user_roles"
    __table_args__ = (
        UniqueConstraint("user_id", "role_id", name="uq_user_roles_user_role"),
        Index("ix_user_roles_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="RESTRICT"), nullable=False)
    granted_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=_now, server_default=func.now())

    user: Mapped[User] = relationship(back_populates="roles")
    role: Mapped[Role] = relationship(back_populates="users", lazy="joined")
