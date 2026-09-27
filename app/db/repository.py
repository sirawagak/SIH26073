"""Data access for users and roles. Slice 1 scope."""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Role, User, UserRole
from app.rbac.roles import ALL_ROLES, DEFAULT_ROLE


def ensure_roles(db: Session) -> None:
    """Idempotently seed the role table."""
    existing = {r.name for r in db.scalars(select(Role))}
    for name in ALL_ROLES:
        if name not in existing:
            db.add(Role(name=name))
    db.commit()


def get_user_by_auth_id(db: Session, auth_user_id: str) -> User | None:
    return db.scalar(select(User).where(User.auth_user_id == auth_user_id))


def create_user(db: Session, *, auth_user_id: str, email: str,
                name: str | None = None, role: str = DEFAULT_ROLE) -> User:
    """Create the app profile for a freshly registered SuperTokens user."""
    user = User(auth_user_id=auth_user_id, email=email, name=name)
    db.add(user)
    db.flush()
    role_row = db.scalar(select(Role).where(Role.name == role))
    if role_row is None:
        role_row = Role(name=role)
        db.add(role_row)
        db.flush()
    db.add(UserRole(user_id=user.id, role_id=role_row.id))
    db.commit()
    db.refresh(user)
    return user


def grant_role(db: Session, user: User, role_name: str) -> User:
    role_row = db.scalar(select(Role).where(Role.name == role_name))
    if role_row is None:
        raise ValueError(f"unknown role {role_name!r}")
    if role_name not in user.role_names:
        db.add(UserRole(user_id=user.id, role_id=role_row.id))
        db.commit()
        db.refresh(user)
    return user
