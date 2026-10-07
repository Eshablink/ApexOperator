from dataclasses import dataclass

import jwt
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError

from apexoperator.security.rbac import Role


@dataclass(frozen=True)
class Principal:
    actor_id: str
    role: Role


class InMemoryAuthenticator:
    """Development authenticator; roles are server-side token mappings, not client claims."""

    def __init__(self, tokens: dict[str, Principal]) -> None:
        self._tokens = dict(tokens)

    def authenticate(self, token: str) -> Principal:
        principal = self._tokens.get(token)
        if principal is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )
        return principal


class JWTAuthenticator:
    """Production authenticator using a server-held HS256 signing secret."""

    def __init__(
        self,
        *,
        secret: str,
        issuer: str | None = None,
        audience: str | None = None,
    ) -> None:
        if len(secret) < 32:
            raise ValueError("JWT secret must be at least 32 characters")
        self._secret = secret
        self._issuer = issuer
        self._audience = audience

    def authenticate(self, token: str) -> Principal:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=["HS256"],
                issuer=self._issuer,
                audience=self._audience,
                options={
                    "require": ["sub", "roles", "exp"],
                },
            )
        except (InvalidTokenError, ValueError) as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="invalid or expired credentials",
                headers={"WWW-Authenticate": "Bearer"},
            ) from exc

        actor_id = payload.get("sub")
        roles = payload.get("roles")
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="token subject is invalid",
                headers={"WWW-Authenticate": "Bearer"},
            )
        if isinstance(roles, str):
            roles = [roles]
        if not isinstance(roles, list) or len(roles) != 1:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="token must contain exactly one supported role",
            )

        try:
            role = Role(str(roles[0]))
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="token role is not supported",
            ) from exc

        return Principal(actor_id=actor_id.strip(), role=role)


bearer_scheme = HTTPBearer(auto_error=False)
