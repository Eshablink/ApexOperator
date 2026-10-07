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
- expired, malformed, incorrectly signed, and over-scoped JWTs.

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
- a `JWT_SECRET` of at least 32 characters.

Development in-memory tokens are not registered in production. Production requests are authenticated by `JWTAuthenticator` using HS256 signatures and standard `sub`, `roles`, and `exp` claims. A token must carry exactly one supported ApexOperator role:

- `AP_CLERK`
- `FINANCE_MANAGER`
- `SYSTEM_ADMIN`

Optional `JWT_ISSUER` and `JWT_AUDIENCE` values further bind tokens to the intended issuer and audience when configured.

Health and readiness remain intentionally unauthenticated so platform probes can reach `/health` and `/ready`.

This is a self-contained JWT mode. An external OIDC provider can replace the credential-validation layer without moving authorization decisions into the client or the LLM.

## Persistence

Tasks are persisted through SQLAlchemy using the configured `DATABASE_URL`. High-value invoices become `PENDING_HUMAN_APPROVAL` only after policy validation and approval submission, and the pending task is recoverable from the persistent task store.

The PostgreSQL integration suite exercises task and audit persistence against a real PostgreSQL service.

## CORS and proxy posture

The standard product surface is served by the same FastAPI origin as the API, so ApexOperator does not need cross-origin browser access for its standard deployment. No wildcard CORS policy is installed.

ApexOperator does not implement its own proxy trust layer; Render/TLS termination is an infrastructure concern. The application does not infer authorization from forwarded headers.

## Current limitations

The audit chain is tamper-evident, not physically immutable.

The OCR layer is an interface boundary; an actual provider must be supplied by deployment.

The application ships a self-contained HS256 JWT mode rather than a full identity-provider stack. Enterprise OIDC/SSO, token revocation, centralized secret management, rate limiting, TLS policy, and operational infrastructure remain deployment-layer extensions.

Those limitations are documented rather than hidden.
