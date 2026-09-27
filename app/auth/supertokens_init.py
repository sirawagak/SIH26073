"""SuperTokens initialisation — the official Python/FastAPI integration.

We implement NO password hashing, NO JWT, NO refresh-token logic and NO session
store. SuperTokens owns all of that.

Recipes enabled now : EmailPassword, Session
Recipes designed for but not yet enabled:
    EmailVerification  - add the recipe, set mode="REQUIRED"
    Passwordless       - OTP / magic link
    MultiFactorAuth    - TOTP / second factor
    WebAuthn           - passkeys
    ThirdParty         - social login
Each is a recipe added to ``recipe_list`` plus frontend config. The session
handling, the user->profile hook and every RBAC check below stay unchanged, so
enabling one later is configuration rather than redesign.
"""
from __future__ import annotations

import logging

from supertokens_python import InputAppInfo, SupertokensConfig, init
from supertokens_python.recipe import emailpassword, session
from supertokens_python.recipe.emailpassword.interfaces import (
    APIInterface as EPAPIInterface,
)
from supertokens_python.recipe.emailpassword.interfaces import (
    APIOptions as EPAPIOptions,
)

from app.core.config import get_settings

logger = logging.getLogger("skyguard.auth")


def _override_emailpassword_apis(original: EPAPIInterface) -> EPAPIInterface:
    """After a successful sign-up, create the matching application profile.

    This is the single seam between SuperTokens (authentication) and our
    database (authorization + profile). It stores the SuperTokens user id and a
    display copy of the email - never a credential.
    """
    original_sign_up = original.sign_up_post

    async def sign_up_post(form_fields, tenant_id, session, should_try_linking_with_session_user,
                           api_options: EPAPIOptions, user_context):
        response = await original_sign_up(
            form_fields, tenant_id, session, should_try_linking_with_session_user,
            api_options, user_context)

        if getattr(response, "user", None) is not None:
            from app.db.repository import create_user, get_user_by_auth_id
            from app.db.session import SessionLocal

            st_user = response.user
            auth_user_id = st_user.id
            email = next((f.value for f in form_fields if f.id == "email"), None) \
                or (st_user.emails[0] if getattr(st_user, "emails", None) else "")
            name = next((f.value for f in form_fields if f.id == "name"), None)

            db = SessionLocal()
            try:
                if get_user_by_auth_id(db, auth_user_id) is None:
                    create_user(db, auth_user_id=auth_user_id, email=email, name=name)
                    logger.info("created application profile for %s", email)
            except Exception:
                # Never fail the sign-up because the profile write failed; the
                # profile is created lazily on first authenticated request.
                logger.exception("could not create application profile for %s", email)
            finally:
                db.close()
        return response

    original.sign_up_post = sign_up_post
    return original


def init_supertokens() -> None:
    s = get_settings()
    init(
        app_info=InputAppInfo(
            app_name=s.app_name,
            api_domain=s.api_domain,
            website_domain=s.website_domain,
            api_base_path="/auth",
            website_base_path="/auth",
        ),
        supertokens_config=SupertokensConfig(
            connection_uri=s.supertokens_connection_uri,
            api_key=s.supertokens_api_key or None,
        ),
        framework="fastapi",
        recipe_list=[
            emailpassword.init(
                sign_up_feature=emailpassword.InputSignUpFeature(
                    form_fields=[emailpassword.InputFormField(id="name", optional=True)]
                ),
                override=emailpassword.InputOverrideConfig(apis=_override_emailpassword_apis),
            ),
            # Cookie-based sessions with anti-CSRF. httpOnly by default; the
            # secure flag follows api_domain scheme in production.
            session.init(cookie_same_site="lax"),
        ],
        mode="asgi",
    )
    logger.info("SuperTokens initialised against %s", s.supertokens_connection_uri)
