"""Admin endpoints. Slice 1 carries the minimum needed to prove RBAC denial.

The full user/station/investigation management surface arrives in later slices.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.deps import require_permission
from app.db.models import User
from app.db.session import get_db
from app.rbac.roles import Permission

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/users")
async def list_users(
    db: Session = Depends(get_db),
    _: User = Depends(require_permission(Permission.MANAGE_USERS)),
) -> dict:
    users = db.scalars(select(User).order_by(User.id)).all()
    return {"users": [{"id": u.id, "email": u.email, "name": u.name,
                       "roles": u.role_names, "is_active": u.is_active}
                      for u in users]}
