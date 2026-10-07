# ApexOperator Deployment

## Render reference deployment

The application is deployed as a Docker web service with a Render PostgreSQL database in the same Singapore region.

Required production environment variables:

```text
APP_ENV=production
LOG_LEVEL=INFO
DATABASE_URL=<Render internal PostgreSQL URL>
JWT_SECRET=<random secret, at least 32 characters>
APEX_PLANNER=mock
```

Optional JWT hardening:

```text
JWT_ISSUER=<expected issuer>
JWT_AUDIENCE=<expected audience>
```

Do not commit secrets or place them in frontend code or browser local storage.

## Authentication

For a production deployment, provision JWTs from an approved identity provider and include:

- `sub`
- `roles` with exactly one supported role
- `exp`

The local demo authenticator is available only outside `APP_ENV=production`.

## Health and readiness

- `/health` — unauthenticated liveness check (GET/HEAD)
- `/ready` — unauthenticated readiness check; validates database access and audit integrity

## Local Docker Compose

```bash
docker compose up --build
```

The compose stack deliberately remains a demo/reference environment and does not require external identity credentials.

## Optional live OpenAI planner

Set:

```text
APEX_PLANNER=openai
OPENAI_API_KEY=<your-key>
OPENAI_MODEL=gpt-6-astra
```

The deterministic runtime still enforces workflow state, identity, step/retry bounds, RBAC, policy, human approval, and audit controls.
