"""Slice 1: authentication, session, RBAC and authenticated inference.

Runs against a live backend on API_BASE (default http://localhost:8000).
Skips cleanly if the backend is not running.

    python3 -m pytest tests/test_slice1.py -v
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import httpx
import pytest

API = os.environ.get("API_BASE", "http://localhost:8000")
PW = "SkyGuard!2026"
REPO = Path(__file__).resolve().parents[1]


def _up() -> bool:
    try:
        return httpx.get(f"{API}/health", timeout=5).status_code == 200
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _up(), reason=f"backend not running at {API}")


def signup(client: httpx.Client, email: str, name: str = "Test User") -> httpx.Response:
    return client.post(f"{API}/auth/signup",
                       headers={"rid": "emailpassword", "st-auth-mode": "cookie"},
                       json={"formFields": [{"id": "email", "value": email},
                                            {"id": "password", "value": PW},
                                            {"id": "name", "value": name}]})


def signin(client: httpx.Client, email: str) -> httpx.Response:
    return client.post(f"{API}/auth/signin",
                       headers={"rid": "emailpassword", "st-auth-mode": "cookie"},
                       json={"formFields": [{"id": "email", "value": email},
                                            {"id": "password", "value": PW}]})


@pytest.fixture
def fresh_user():
    email = f"slice1-{uuid.uuid4().hex[:10]}@skyguard.test"
    with httpx.Client(timeout=30, follow_redirects=True) as c:
        r = signup(c, email)
        assert r.status_code == 200 and r.json()["status"] == "OK", r.text
        yield c, email, r.json()["user"]["id"]


# ---------------------------------------------------------------- authentication
def test_health_is_public():
    assert httpx.get(f"{API}/health", timeout=10).json() == {"status": "ok"}


def test_protected_endpoints_reject_anonymous():
    for path in ("/api/v1/me", "/api/v1/model", "/api/v1/admin/users"):
        assert httpx.get(f"{API}{path}", timeout=10).status_code == 401, path
    r = httpx.post(f"{API}/api/v1/predict", timeout=10,
                   json={"observations": [{"time": "2023-09-24T00:00:00Z", "temp_c": 25,
                                           "slp_hpa": 1005, "rh_pct": 90}]})
    assert r.status_code == 401


def test_signup_creates_session_and_profile(fresh_user):
    client, email, auth_id = fresh_user
    me = client.get(f"{API}/api/v1/me")
    assert me.status_code == 200
    body = me.json()
    assert body["email"] == email
    assert body["auth_user_id"] == auth_id
    assert body["roles"] == ["VIEWER"], "new users must default to VIEWER"


def test_no_credential_material_is_exposed(fresh_user):
    client, _, _ = fresh_user
    body = client.get(f"{API}/api/v1/me").json()
    blob = json.dumps(body).lower()
    for leak in ("password", "hash", "salt", "refresh", "secret", "token"):
        assert leak not in blob, f"/me leaked {leak!r}"


def test_signin_after_signout(fresh_user):
    client, email, _ = fresh_user
    assert client.post(f"{API}/auth/signout", json={}).status_code == 200
    assert client.get(f"{API}/api/v1/me").status_code == 401, "session must be revoked"
    assert signin(client, email).status_code == 200
    assert client.get(f"{API}/api/v1/me").status_code == 200


def test_wrong_password_is_rejected():
    email = f"slice1-{uuid.uuid4().hex[:10]}@skyguard.test"
    with httpx.Client(timeout=30) as c:
        signup(c, email)
        c.post(f"{API}/auth/signout", json={})
        r = c.post(f"{API}/auth/signin", headers={"rid": "emailpassword"},
                   json={"formFields": [{"id": "email", "value": email},
                                        {"id": "password", "value": "wrong-password-123"}]})
        assert r.json()["status"] == "WRONG_CREDENTIALS_ERROR"


# ---------------------------------------------------------------- authorization
def test_viewer_is_denied_admin_route(fresh_user):
    client, _, _ = fresh_user
    r = client.get(f"{API}/api/v1/admin/users")
    assert r.status_code == 403
    assert r.json()["error"] == "forbidden"
    assert "VIEWER" in r.json()["your_roles"]


def test_role_is_not_client_controllable(fresh_user):
    """A user cannot promote themselves by asserting a role in the request."""
    client, _, _ = fresh_user
    r = client.get(f"{API}/api/v1/admin/users",
                   headers={"X-Role": "ADMIN", "X-Roles": "ADMIN", "Role": "ADMIN"})
    assert r.status_code == 403, "role must come from the database, never a header"


def test_permissions_match_role(fresh_user):
    client, _, _ = fresh_user
    perms = set(client.get(f"{API}/api/v1/me").json()["permissions"])
    assert {"VIEW_DASHBOARD", "RUN_PREDICTION"} <= perms
    assert "MANAGE_USERS" not in perms


# ---------------------------------------------------------------- ML integration
def test_authenticated_predict_matches_frozen_contract(fresh_user):
    client, _, _ = fresh_user
    payload = json.loads((REPO / "examples" / "sample_input.json").read_text())
    r = client.post(f"{API}/api/v1/predict", json=payload)
    assert r.status_code == 200
    got = r.json()
    expected = json.loads((REPO / "examples" / "sample_output.json").read_text())

    volatile = {"scored_at", "model_version"}

    def strip(o):
        if isinstance(o, dict):
            return {k: strip(v) for k, v in o.items() if k not in volatile}
        if isinstance(o, list):
            return [strip(v) for v in o]
        return o

    assert strip(got["results"]) == strip(expected["results"]), "ML contract changed"
    assert strip(got["summary"]) == strip(expected["summary"])
    assert got["model"]["model_version"], "model_version must be stamped"


def test_predict_rejects_garbage(fresh_user):
    client, _, _ = fresh_user
    bad = {"observations": [{"time": "2023-09-24T00:00:00Z", "slp_hpa": 1005, "rh_pct": 90}]}
    r = client.post(f"{API}/api/v1/predict", json=bad)
    assert r.status_code == 422
    assert r.json()["error"] == "validation_failed"


def test_fault_magnitudes_are_not_rejected(fresh_user):
    """A faulty sensor is what the system exists to detect - it must reach the model."""
    client, _, _ = fresh_user
    obs = [{"time": "2023-09-24T00:00:00Z", "temp_c": 42.8, "slp_hpa": 960.0, "rh_pct": 2.0}]
    assert client.post(f"{API}/api/v1/predict", json={"observations": obs}).status_code == 200


def test_model_info_reports_version_and_caveats(fresh_user):
    client, _, _ = fresh_user
    info = client.get(f"{API}/api/v1/model").json()
    assert len(info["model_version"]) == 12
    assert info["n_features"] == 16
    assert info["n_estimators"] == 200
    assert "requires human verification" in info["assessment_note"]
    assert info["caveats"], "model caveats must be surfaced, not hidden"
