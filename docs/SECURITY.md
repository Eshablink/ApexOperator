# ApexOperator Security Model

## Threats considered

The evaluation suite covers:

- unauthorized role/permission combinations;
- attempts to execute handlers without permission;
- malformed tool input;
- audit payload tampering;
- duplicate audit event IDs;
- persistent audit deletion and insertion;
- sequence/reordering tampering;
- invalid approval state transitions;
- unbounded runtime plans;
- unsafe document paths;
- MIME/magic mismatch;
- browser submission that does not reach the expected post-action state;
- expired, malformed, incorrectly signed, and over-scoped JWTs;
- revoked database sessions;
- CSRF failures on state-changing requests.

## Security posture

ApexOperator is intentionally designed around defense in depth:

1. validate input;
2. resolve identity on the server;
3. check permission;
4. enforce deterministic policy;
5. bound execution;
6. verify the external result;
7. persist an auditable record.

No single LLM response is trusted to provide all of these controls.

## Production authentication boundary

When `APP_ENV=production`, application startup requires:

- a persistent non-SQLite `DATABASE_URL`;
- a `JWT_SECRET` of at least 32 characters;
- `APEX_BOOTSTRAP_EMAIL`;
- `APEX_BOOTSTRAP_PASSWORD_HASH` using the bundled scrypt format.

A database-backed user record is bootstrapped at startup if it does not already exist. Production login verifies the password hash and creates a revocable session in the database. The signed JWT is delivered only in an HttpOnly, Secure, SameSite=Lax cookie. A separate CSRF cookie is required for state-changing requests.

JWT validation requires:

- `sub`;
- `roles` with exactly one supported role;
- `sid`;
- `exp`.

Optional `JWT_ISSUER` and `JWT_AUDIENCE` values can further bind tokens to the intended issuer/audience.

Development in-memory tokens are never registered in production.

## Health and readiness

- `/health` — unauthenticated liveness endpoint for platform probes;
- `/ready` — unauthenticated readiness endpoint that checks persistence access and audit integrity.

## Persistence

Tasks and audit events use the configured SQLAlchemy database. High-value invoices are persisted as `PENDING_HUMAN_APPROVAL` before a reviewer can approve or reject them.

The test suite includes real PostgreSQL integration and a restart/reinitialization persistence check.

## CORS and proxy posture

The standard UI and API are served from the same FastAPI origin, so no browser CORS policy is required. Wildcard CORS is intentionally not installed.

Render/TLS termination is treated as infrastructure. The application does not use forwarded headers as an authorization source.

## Current limitations

The audit chain is tamper-evident, not physically immutable.

The OCR layer is an interface boundary; an actual provider must be supplied by deployment.

The self-contained JWT mode provides application authentication, but enterprise OIDC/SSO, centralized secret management, rate limiting, and broader IAM lifecycle management remain deployment-layer extensions.

Those limitations are documented rather than hidden.
