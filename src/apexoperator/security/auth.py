from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import base64
import hashlib
import hmac
import secrets
from typing import Any

import jwt
from fastapi import HTTPException, status
from jwt import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from apexoperator.persistence.models import AuthSessionRecord, UserRecord
from apexoperator.security.rbac import Role


@dataclass(frozen=True)
class Principal:
    actor_id: str
    role: Role
    organization_id: str = "default"


class InMemoryAuthenticator:
    def __init__(self, tokens: dict[str, Principal]) -> None:
        self._tokens = dict(tokens)

    def authenticate(self, token: str) -> Principal:
        principal = self._tokens.get(token)
        if principal is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid credentials", headers={"WWW-Authenticate": "Bearer"})
        return principal


def hash_password(password: str) -> str:
    if len(password) < 12:
        raise ValueError("password must be at least 12 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$v1$16384$8$1$" + base64.urlsafe_b64encode(salt).decode() + "$" + base64.urlsafe_b64encode(digest).decode()


def verify_password(password: str, encoded: str) -> bool:
    try:
        scheme, version, n, r, p, salt_b64, digest_b64 = encoded.split("$", 6)
        if scheme != "scrypt" or version != "v1":
            return False
        salt = base64.urlsafe_b64decode(salt_b64.encode())
        expected = base64.urlsafe_b64decode(digest_b64.encode())
        actual = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=int(n), r=int(r), p=int(p), dklen=len(expected))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def ensure_bootstrap_user(session_factory: sessionmaker, *, email: str, password_hash: str, role: Role, organization_id: str = "default") -> None:
    normalized = email.strip().lower()
    if not normalized:
        raise ValueError("bootstrap email cannot be empty")
    with session_factory.begin() as session:
        existing = session.scalar(select(UserRecord).where(UserRecord.email == normalized))
        if existing is None:
            session.add(UserRecord(actor_id=f"user-{secrets.token_hex(8)}", email=normalized, organization_id=organization_id, role=role.value, password_hash=password_hash, is_active=True))
        elif not existing.is_active:
            raise ValueError("bootstrap user is disabled")


class JWTAuthenticator:
    SESSION_COOKIE = "apexoperator_session"
    CSRF_COOKIE = "apexoperator_csrf"

    def __init__(self, *, session_factory: sessionmaker | None = None, secret: str, issuer: str | None = None, audience: str | None = None, session_minutes: int = 60, cookie_secure: bool = True) -> None:
        if len(secret) < 32:
            raise ValueError("JWT secret must be at least 32 characters")
        self._sessions = session_factory
        self._secret = secret
        self._issuer = issuer
        self._audience = audience
        self._session_minutes = session_minutes
        self.cookie_secure = cookie_secure

    def _decode(self, token: str) -> dict[str, Any]:
        try:
            options = {"require": ["sub", "roles", "exp", "sid"], "verify_aud": bool(self._audience)}
            return jwt.decode(token, self._secret, algorithms=["HS256"], issuer=self._issuer, audience=self._audience, options=options)
        except (InvalidTokenError, ValueError) as exc:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid or expired credentials", headers={"WWW-Authenticate": "Bearer"}) from exc

    def login(self, email: str, password: str) -> tuple[str, Principal, str, int]:
        normalized = email.strip().lower()
        if self._sessions is None:
            raise RuntimeError("database session factory is required for login")
        with self._sessions.begin() as session:
            user = session.scalar(select(UserRecord).where(UserRecord.email == normalized))
            if user is None or not user.is_active or not verify_password(password, user.password_hash):
                raise HTTPException(status_code=401, detail="invalid email or password", headers={"WWW-Authenticate": "Bearer"})
            try:
                role = Role(user.role)
            except ValueError as exc:
                raise HTTPException(status_code=403, detail="account role is not supported") from exc
            now = datetime.now(timezone.utc)
            expires = now + timedelta(minutes=self._session_minutes)
            session_id = secrets.token_urlsafe(32)
            csrf_token = secrets.token_urlsafe(32)
            session.add(AuthSessionRecord(session_id=session_id, actor_id=user.actor_id, csrf_token=csrf_token, expires_at=expires.isoformat(), created_at=now.isoformat()))
            principal = Principal(user.actor_id, role, user.organization_id)
        payload: dict[str, Any] = {"sub": principal.actor_id, "roles": [principal.role.value], "sid": session_id, "iat": int(now.timestamp()), "exp": int(expires.timestamp())}
        if self._issuer: payload["iss"] = self._issuer
        if self._audience: payload["aud"] = self._audience
        return jwt.encode(payload, self._secret, algorithm="HS256"), principal, csrf_token, self._session_minutes * 60

    def authenticate(self, token: str) -> Principal:
        payload = self._decode(token)
        session_id, actor_id = str(payload["sid"]), str(payload["sub"])
        roles = payload.get("roles")
        if not isinstance(roles, list) or len(roles) != 1:
            raise HTTPException(status_code=403, detail="token must contain exactly one supported role")
        try:
            role = Role(str(roles[0]))
        except ValueError as exc:
            raise HTTPException(status_code=403, detail="token role is not supported") from exc
        if self._sessions is None:
            return Principal(actor_id, role)
        with self._sessions() as session:
            auth_session = session.get(AuthSessionRecord, session_id)
            user = session.get(UserRecord, actor_id)
            if auth_session is None or user is None or not user.is_active:
                raise HTTPException(status_code=401, detail="session is no longer valid", headers={"WWW-Authenticate": "Bearer"})
            expires = datetime.fromisoformat(auth_session.expires_at)
            if auth_session.revoked_at or expires <= datetime.now(timezone.utc):
                raise HTTPException(status_code=401, detail="session is no longer valid", headers={"WWW-Authenticate": "Bearer"})
            if auth_session.actor_id != actor_id or user.role != role.value:
                raise HTTPException(status_code=401, detail="session identity mismatch")
            return Principal(actor_id, role, user.organization_id)

    def csrf_for_session(self, token: str) -> str:
        if self._sessions is None: raise RuntimeError("database session factory is required for csrf retrieval")
        payload = self._decode(token)
        with self._sessions() as session:
            auth_session = session.get(AuthSessionRecord, str(payload["sid"]))
            if auth_session is None or auth_session.revoked_at: raise HTTPException(status_code=401, detail="session is no longer valid")
            return auth_session.csrf_token

    def logout(self, token: str) -> None:
        if self._sessions is None: raise RuntimeError("database session factory is required for logout")
        payload = self._decode(token)
        with self._sessions.begin() as session:
            auth_session = session.get(AuthSessionRecord, str(payload["sid"]))
            if auth_session and not auth_session.revoked_at: auth_session.revoked_at = datetime.now(timezone.utc).isoformat()


bearer_scheme = None
