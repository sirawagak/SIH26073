"""Request dependencies: session -> application user -> permission.

Every sensitive check happens here, server-side. The frontend's role awareness is
presentation only and is never trusted.
"""
from __future__ import annotations

from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from supertokens_python.recipe.session import SessionContainer
from supertokens_python.recipe.session.framework.fastapi import verify_session

from app.db.models import User
from app.db.repository import create_user, get_user_by_auth_id
from app.db.session import get_db
from app.rbac.roles import Permission, Role, permissions_for


async def current_user(
    st_session: SessionContainer = Depends(verify_session()),
    db: Session = Depends(get_db),
) -> User:
    """Resolve the SuperTokens session to an application profile.

    If the profile is missing (e.g. the post-sign-up hook failed), it is created
    lazily here so a valid session is never left without a profile.
    """
    auth_user_id = st_session.get_user_id()
    user = get_user_by_auth_id(db, auth_user_id)
    if user is None:
        email = ""
        try:
            from supertokens_python.recipe.emailpassword.asyncio import get_user_by_id
            st_user = await get_user_by_id(auth_user_id)
            if st_user is not None and getattr(st_user, "emails", None):
                email = st_user.emails[0]
        except Exception:
            pass
        user = create_user(db, auth_user_id=auth_user_id, email=email)
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            detail={"error": "account_disabled",
                                    "message": "This account has been disabled."})
    return user


def require_permission(perm: Permission):
    """Dependency factory enforcing a single permission."""

    async def _check(user: User = Depends(current_user)) -> User:
        if perm not in permissions_for(user.role_names):
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={"error": "forbidden",
                        "message": f"Requires permission {perm.value}.",
                        "your_roles": user.role_names})
        return user

    return _check


def require_role(*roles: Role):
    async def _check(user: User = Depends(current_user)) -> User:
        if not set(user.role_names) & {r.value for r in roles}:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail={"error": "forbidden",
                        "message": f"Requires one of: {', '.join(r.value for r in roles)}.",
                        "your_roles": user.role_names})
        return user

    return _check
