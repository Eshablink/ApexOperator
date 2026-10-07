import json
import time

import jwt

from apexoperator.config import settings
from apexoperator.persistence.database import make_engine, make_session_factory
from apexoperator.security.auth import JWTAuthenticator, ensure_bootstrap_user, hash_password
from apexoperator.security.rbac import Role


def test_database_auth_login_creates_revocable_session(tmp_path, monkeypatch):
    database_url = f"sqlite:///{tmp_path / 'auth.sqlite3'}"
    engine = make_engine(database_url)
    from apexoperator.persistence.database import init_database
    init_database(engine)
    sessions = make_session_factory(engine)

    password = "VeryStrong!DemoPassword123"
    ensure_bootstrap_user(
        sessions,
        email="owner@example.com",
        password_hash=hash_password(password),
        role=Role.FINANCE_MANAGER,
    )

    authenticator = JWTAuthenticator(
        session_factory=sessions,
        secret="s" * 48,
        session_minutes=30,
        cookie_secure=False,
    )
    token, principal, csrf, max_age = authenticator.login("owner@example.com", password)
    assert principal.role is Role.FINANCE_MANAGER
    assert csrf
    assert max_age == 1800
    assert authenticator.authenticate(token) == principal

    authenticator.logout(token)

    try:
        authenticator.authenticate(token)
    except Exception as error:
        assert getattr(error, "status_code", None) == 401
    else:
        raise AssertionError("revoked session remained valid")

    engine.dispose()


def test_settings_require_bootstrap_identity_in_production(monkeypatch):
    original = {
        "app_env": settings.app_env,
        "database_url": settings.database_url,
        "jwt_secret": settings.jwt_secret,
        "bootstrap_email": settings.bootstrap_email,
        "bootstrap_password_hash": settings.bootstrap_password_hash,
    }
    try:
        settings.app_env = "production"
        settings.database_url = "postgresql+psycopg://user:pass@db/app"
        settings.jwt_secret = "x" * 48
        settings.bootstrap_email = None
        settings.bootstrap_password_hash = None

        from pydantic import ValidationError
        from apexoperator.config import Settings
        import pytest

        with pytest.raises(ValidationError):
            Settings(
                app_env=settings.app_env,
                database_url=settings.database_url,
                jwt_secret=settings.jwt_secret,
            )
    finally:
        for key, value in original.items():
            setattr(settings, key, value)
