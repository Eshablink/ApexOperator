from dataclasses import dataclass
from fastapi import HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

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
            )
        return principal


bearer_scheme = HTTPBearer(auto_error=False)
