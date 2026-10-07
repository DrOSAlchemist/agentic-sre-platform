# Security model

## Current trust boundary

This is a single-user local CLI, not an authenticated service. Synthetic evidence is
operator supplied. It proves control logic, not AWS provenance or production readiness.
Run it in a private directory on a trusted host; SQLite data is not encrypted and
the database owner can change records. Application audit writes are append-only,
but the log is neither immutable nor cryptographically authenticated.

| Threat | Implemented boundary | Remaining limitation |
|---|---|---|
| Log/model prompt injection | No free-text log ingestion or model tool execution; explanation cannot alter decisions | Displayed explanation prose can still mislead a human |
| Terraform injection | Fixed resource template and quota allowlist; integer-only target | Provider/account/region and existing state need operator review |
| Excessive quota request | Target capped at 2x current and 1024 vCPUs | Quota is not a spending budget; capacity can still increase cost |
| False root cause | Requires correlated scheduling, provisioning, API error and usage signals | Synthetic inputs can be forged; collectors are not implemented |
| Replay/conflicting changes | Scoped key, canonical payload comparison and transactional state changes | Local database administrator is trusted |
| False recovery | Every recovery signal required, newer observation and no timestamp regression | No stability window or live collector in this release |
| Oversized/malformed input | 64 KiB input cap, exact schema, duplicate JSON rejection, bounded fields | No multi-tenant quotas because there is no service |
| Secret exposure | No credentials or remote requests required; narrow explanation credential-pattern rejection | Not complete DLP; do not ingest real secrets |
| Agent outage | Deterministic path and manual runbook remain usable | Cloud alerts and runbooks must be independently deployed later |

## Planned production controls

- Read-only investigation IAM/RBAC; no cluster-admin or cloud mutation tools.
- Separate scoped GitHub App for proposals and deployment OIDC identity.
- Human approvals, protected branches/environments, and deny-by-default policy.
- Short-lived workload identity; narrowly bound JWT audiences and claims.
- Encrypted secret storage, Kubernetes Secret RBAC and encryption at rest.
- Signed images, SBOM/provenance, scanning, and enforcing admission verification.
- Independent audit sink with retention/access policy; encrypted incident evidence.
- Pre-model redaction, source attribution, tool-result schemas and bounded budgets.
- Explicit timeout/retry/dead-letter handling and a manual escalation path.
- Tested database, Vault, identity and storage backups/restores.

These are requirements, not claims about implemented controls. No production
deployment, external security audit or penetration test has been performed.

## Reporting issues

Do not publish credentials or sensitive incident data in an issue. A private
reporting channel must be configured by the repository owner before public release.
