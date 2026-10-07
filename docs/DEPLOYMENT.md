# ApexOperator Deployment

## Render reference deployment

The application is deployed as a Docker web service with a Render PostgreSQL database in the same Singapore region.

### Required environment

```text
APP_ENV=production
LOG_LEVEL=INFO
DATABASE_URL=<Render internal PostgreSQL URL>
JWT_SECRET=<random secret, at least 32 characters>
APEX_BOOTSTRAP_EMAIL=<operator email>
APEX_BOOTSTRAP_PASSWORD_HASH=<scrypt hash from scripts/make_password_hash.py>
APEX_BOOTSTRAP_ROLE=FINANCE_MANAGER
APEX_SESSION_MINUTES=60
APEX_PLANNER=mock
```

Optional:

```text
JWT_ISSUER=<expected issuer>
JWT_AUDIENCE=<expected audience>
OPENAI_API_KEY=<provider key>
OPENAI_MODEL=gpt-6-astra
```

Do not commit secrets or place them in frontend code or browser storage.

### Bootstrap the first production user

Generate a password hash locally:

```bash
PYTHONPATH=src python scripts/make_password_hash.py
```

Paste the resulting hash into Render as `APEX_BOOTSTRAP_PASSWORD_HASH`.

The bootstrap user is created in PostgreSQL on startup if it does not exist already.

## Authentication

Production login uses:

- database-backed user records;
- scrypt password verification;
- signed HS256 JWTs;
- revocable database sessions;
- HttpOnly/Secure/SameSite cookies;
- a CSRF token cookie/header for state-changing requests;
- deterministic server-side RBAC.

The development role-picker remains available only outside production.

## Health and readiness

- `/health` — unauthenticated liveness (GET/HEAD)
- `/ready` — unauthenticated readiness; checks database access and audit integrity

## Local Docker Compose

```bash
docker compose up --build
```

The compose stack remains a deterministic demo/reference environment.

## UI/UX

The public product surface uses a responsive, keyboard-friendly control-room experience with live API status, audit integrity feedback, secure-session state, and a command palette on Ctrl/Cmd+K.

## Cold-start behavior

The Render free tier may sleep an idle service. The control room treats the first request as a recoverable cold start: it shows a waking message, uses a bounded request timeout, and exposes a Retry action rather than leaving visitors on indefinite placeholders.

For portfolio/demo availability, an external uptime monitor such as UptimeRobot can request the public `/health` endpoint every 10 minutes. This is optional and should be configured outside the repository; no monitoring credentials belong in the app.

## HTTP security headers

The FastAPI app adds:

- `Content-Security-Policy`
- `Strict-Transport-Security` in HTTPS production requests
- `X-Content-Type-Options: nosniff`
- `X-Frame-Options: DENY`
- `Referrer-Policy: strict-origin-when-cross-origin`
- restrictive `Permissions-Policy`

## Planner selection

Set `APEX_PLANNER=auto` to prefer the configured OpenAI planner and fall back to the deterministic planner when no provider key exists. The control room also exposes a per-run planner selector; selecting the live planner requires the deployment to have `OPENAI_API_KEY` configured.
