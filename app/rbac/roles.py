"""Application roles and the permission matrix.

SuperTokens answers "who are you". This module answers "what may you do".
Authorization lives here, in our database, never in the frontend.
"""
from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    ADMIN = "ADMIN"
    SCIENTIST_REVIEWER = "SCIENTIST_REVIEWER"
    STATION_OPERATOR = "STATION_OPERATOR"
    VIEWER = "VIEWER"


DEFAULT_ROLE = Role.VIEWER
ALL_ROLES = [r.value for r in Role]


class Permission(StrEnum):
    # read
    VIEW_DASHBOARD = "VIEW_DASHBOARD"
    VIEW_STATIONS = "VIEW_STATIONS"
    RUN_PREDICTION = "RUN_PREDICTION"
    VIEW_INVESTIGATIONS = "VIEW_INVESTIGATIONS"
    # review (later slices)
    REVIEW_ASSIGNED = "REVIEW_ASSIGNED"
    COMMENT_OPERATIONAL = "COMMENT_OPERATIONAL"
    # admin (later slices)
    MANAGE_USERS = "MANAGE_USERS"
    MANAGE_STATIONS = "MANAGE_STATIONS"
    MANAGE_INVESTIGATIONS = "MANAGE_INVESTIGATIONS"
    VIEW_AUDIT = "VIEW_AUDIT"


ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.VIEWER: {
        Permission.VIEW_DASHBOARD, Permission.VIEW_STATIONS,
        Permission.RUN_PREDICTION, Permission.VIEW_INVESTIGATIONS,
    },
    Role.STATION_OPERATOR: {
        Permission.VIEW_DASHBOARD, Permission.VIEW_STATIONS,
        Permission.RUN_PREDICTION, Permission.VIEW_INVESTIGATIONS,
        Permission.COMMENT_OPERATIONAL,
    },
    Role.SCIENTIST_REVIEWER: {
        Permission.VIEW_DASHBOARD, Permission.VIEW_STATIONS,
        Permission.RUN_PREDICTION, Permission.VIEW_INVESTIGATIONS,
        Permission.REVIEW_ASSIGNED,
    },
    Role.ADMIN: set(Permission),
}


def permissions_for(roles: list[str]) -> set[Permission]:
    out: set[Permission] = set()
    for r in roles:
        try:
            out |= ROLE_PERMISSIONS[Role(r)]
        except ValueError:
            continue
    return out


def has_permission(roles: list[str], perm: Permission) -> bool:
    return perm in permissions_for(roles)
