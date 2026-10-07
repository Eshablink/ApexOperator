import json
import time

import jwt
import pytest

from apexoperator.config import Settings
from apexoperator.security.auth import JWTAuthenticator, Principal
from apexoperator.security.rbac import Role


def test_production_settings_require_persistent_database():
    with pytest.raises(ValueError, match="persistent non-SQLite DATABASE_URL"):
        Settings(
            app_env="production",
            database_url="sqlite:///./local.sqlite3",
            jwt_secret="x" * 48,
        )


def test_production_settings_require_strong_jwt_secret():
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(
            app_env="production",
            database_url="postgresql+psycopg://user:pass@db/app",
            jwt_secret="too-short",
        )


def test_production_settings_accept_strong_jwt_secret():
    settings = Settings(
        app_env="production",
        database_url="postgresql+psycopg://user:pass@db/app",
        jwt_secret="x" * 48,
        bootstrap_email="owner@example.com",
        bootstrap_password_hash="scrypt$v1$16384$8$1$c2FsdA==$ZGlnZXN0",
    )
    assert settings.app_env == "production"


def make_token(secret: str, *, role=Role.FINANCE_MANAGER, expires_in=300, **claims):
    payload = {
        "sub": "manager-1",
        "roles": [role.value],
        "sid": "test-session",
        "exp": int(time.time()) + expires_in,
        **claims,
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def test_jwt_authenticator_returns_server_side_principal():
    secret = "s" * 48
    authenticator = JWTAuthenticator(secret=secret)
    principal = authenticator.authenticate(make_token(secret))
    assert principal == Principal("manager-1", Role.FINANCE_MANAGER)


def test_jwt_authenticator_rejects_wrong_signature():
    authenticator = JWTAuthenticator(secret="s" * 48)
    token = make_token("t" * 48)

    with pytest.raises(Exception) as error:
        authenticator.authenticate(token)

    assert getattr(error.value, "status_code", None) == 401


def test_jwt_authenticator_requires_single_supported_role():
    secret = "s" * 48
    authenticator = JWTAuthenticator(secret=secret)
    token = jwt.encode(
        {
            "sub": "manager-1",
            "roles": [Role.FINANCE_MANAGER.value, Role.SYSTEM_ADMIN.value],
            "sid": "test-session",
            "exp": int(time.time()) + 300,
        },
        secret,
        algorithm="HS256",
    )

    with pytest.raises(Exception) as error:
        authenticator.authenticate(token)

    assert getattr(error.value, "status_code", None) == 403


def test_jwt_authenticator_rejects_expired_token():
    secret = "s" * 48
    authenticator = JWTAuthenticator(secret=secret)
    token = make_token(secret, expires_in=-1)

    with pytest.raises(Exception) as error:
        authenticator.authenticate(token)

    assert getattr(error.value, "status_code", None) == 401


def test_health_route_is_available_to_unauthenticated_clients(tmp_path):
    from fastapi.testclient import TestClient
    from apexoperator.api.main import create_app

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "incoming_batch.json").write_text(
        json.dumps({"invoices": []}),
        encoding="utf-8",
    )
    client = TestClient(
        create_app(
            workspace_dir=workspace,
            database_path=tmp_path / "app.sqlite3",
        )
    )

    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

    head = client.head("/health")
    assert head.status_code == 200
