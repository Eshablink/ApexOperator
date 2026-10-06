# ApexOperator Deployment

## Docker Compose

The reference deployment runs the application with PostgreSQL while keeping the planner in deterministic mock mode by default.

```bash
docker compose up --build
```

Then open:

- `http://127.0.0.1:8000/` — product landing page
- `http://127.0.0.1:8000/docs` — API docs
- `http://127.0.0.1:8000/ready` — readiness probe

The compose stack deliberately does not require an external AI credential.

## Optional live OpenAI planner

Set these environment variables for the same application image:

```text
APEX_PLANNER=openai
OPENAI_API_KEY=<your-key>
OPENAI_MODEL=gpt-6-astra
```

The live planner is optional. The deterministic runtime still enforces the allowed tool sequence, invoice identity, step bound, retry bound, RBAC, policy engine, human approval state, and audit chain.

Do not place API keys in source control, the frontend, or browser local storage.

## Production hardening still required

This repository is a portfolio/reference implementation. A real deployment should add a real identity provider, TLS termination, secret management, rate limiting, centralized observability, durable externalized audit controls, and operational alerting.
