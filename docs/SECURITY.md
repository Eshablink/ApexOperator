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
- browser submission that does not reach the expected post-action state.

## Security posture

ApexOperator is intentionally designed around **defense in depth**:

1. validate input;
2. resolve identity on the server;
3. check permission;
4. enforce deterministic policy;
5. bound execution;
6. verify the external result;
7. persist an auditable record.

No single LLM response is trusted to provide all of these controls.

## Current limitations

The local authenticator is a development mechanism, not a production identity provider.

The audit chain is tamper-evident, not physically immutable.

The OCR layer is an interface boundary; an actual provider must be supplied by deployment.

Secrets, TLS termination, enterprise identity, rate limiting, and operational infrastructure still belong to the deployment layer.

Those limitations are documented rather than hidden.
