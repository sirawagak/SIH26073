"""Identity + capability endpoint. The protected endpoint for Slice 1."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.deps import current_user
from app.db.models import User
from app.rbac.roles import permissions_for

router = APIRouter(tags=["identity"])


@router.get("/me")
async def me(user: User = Depends(current_user)) -> dict:
    return {
        "id": user.id,
        "auth_user_id": user.auth_user_id,
        "email": user.email,
        "name": user.name,
        "roles": user.role_names,
        "permissions": sorted(p.value for p in permissions_for(user.role_names)),
        "created_at": user.created_at.isoformat(),
    }
