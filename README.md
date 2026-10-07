# Agentic SRE Platform

An evidence-backed SRE demonstrator with deterministic diagnosis, bounded Terraform
proposals, durable incident tracking, and independently evaluated recovery signals.
The first release is **offline and synthetic**: no AWS, Kubernetes, GitHub, MCP, or
model API is called. The agent-assisted architecture is a roadmap, not a claim that
live integrations already exist.

## Five-minute demo

Use Python 3.12+ for new installations. The implementation remains compatible with
Python 3.9 for existing local environments, but that runtime is end-of-life and
should not be used for deployment.

```sh
PYTHONPATH=src python3 -m sre_platform --db incidents.db demo
PYTHONPATH=src python3 -m unittest discover -s tests -v
```

The demo emits JSON showing:

1. Pending pods + failed NodeClaims + EC2 limit error + exhausted vCPU quota.
2. An evidence-backed diagnosis and a Terraform **proposal**, not execution.
3. `awaiting_recovery` while the effective quota has not increased.
4. `recovered` only after a newer synthetic observation passes every recovery check.
5. Four persisted audit events.

Each demo uses a fresh synthetic incident key. The database is ignored by Git.
There is no requirement to have cloud credentials or an AI subscription.

For an installed CLI:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/sre-platform --db incidents.db demo
```

## What is implemented

| Capability | Evidence |
|---|---|
| Strict input boundary | Exact fields, bounded integers, UTC-aware freshness, duplicate-key and size checks |
| Root-cause guard | Abstains on IAM failures, capacity failures, missing causal signals |
| Proposal policy | Standard On-Demand quota only; target > current, <= 2x current and <= 1024 vCPUs |
| Durable state | Transactional SQLite, scoped incident keys, idempotent investigation and proposal replay |
| Recovery gates | New observation, effective quota, successful launches, no Pending pods/failed NodeClaims/errors, healthy application |
| Optional AI boundary | Offline explanation JSON cannot change diagnosis, evidence IDs, or actions |
| CI | Ruff lint, Bandit source scan, unit/integration tests, compilation, package installation and executable demo |

The optional explanation boundary is **not a live LLM integration** or a reliable
general-purpose prompt-injection detector. Deterministic controls own decisions.
Free-text logs and arbitrary tool instructions are deliberately outside the input contract.

## CLI

```sh
PYTHONPATH=src python3 -m sre_platform --help
PYTHONPATH=src python3 -m sre_platform investigate evidence.json
PYTHONPATH=src python3 -m sre_platform propose INCIDENT_ID --target-vcpus 64
PYTHONPATH=src python3 -m sre_platform verify INCIDENT_ID recovery.json
PYTHONPATH=src python3 -m sre_platform show INCIDENT_ID
PYTHONPATH=src python3 -m sre_platform audit INCIDENT_ID
```

All commands accept global `--db PATH` **before** the subcommand. Input schema is
illustrated by [the fixture](examples/quota-exhausted.json); update `observed_at`
to a current timestamp for manual investigation. The historical fixture is for
repeatable tests; the demo creates current observations automatically.

Exit codes: `0` successful operation, `2` input/storage/policy error,
`3` verification ran but recovery is incomplete. A successful proposal command
does not mean that approval, submission, or recovery occurred.

`investigate --explanation explanation.json` accepts exactly:

```json
{
  "cause": "ec2_vcpu_quota_exhausted",
  "evidence_ids": ["pending_pods", "failed_nodeclaims", "launch_error", "used_vcpus", "quota_vcpus"],
  "summary": "The scoped signals support a quota investigation."
}
```

Accepted prose remains untrusted, is only displayed, and never enters a remediation
decision. Credential-pattern rejection is defense-in-depth, not complete redaction.

## Development checks

```sh
.venv/bin/python -m pip install '.[dev]'
.venv/bin/ruff check .
.venv/bin/bandit -q -r src
PYTHONPATH=src .venv/bin/python -m unittest discover -s tests -v
```

The runtime has no third-party dependencies. Development tools are explicitly pinned;
review and refresh those pins periodically. Static scans do not constitute a security
audit or prove that a future cloud integration is safe.

CI uses the explicit Ubuntu 24.04 runner image and SHA-pinned, Node.js 24-based
checkout/setup-python actions. Checkout does not persist Git credentials.
Review runner support and action pins periodically rather than relying on
automatic `ubuntu-latest` migrations.

## Secure GitOps integration roadmap

See [architecture and staged GitOps delivery](docs/architecture.md), the
[threat model](docs/security-model.md), and [manual incident runbook](docs/runbook.md).

Argo CD, Keycloak, Harbor, Vault + Vault Secrets Operator, CloudNativePG,
cert-manager, and optional Longhorn form the intended delivery plane. GitHub
Actions is the initial CI target; GitLab CI is a later adapter.
**No deployable platform manifests are included in this release.**

## Publishing

This directory is not automatically published. Before creating a public repository:

- Confirm rights to all contributed content; this project uses the [MIT License](LICENSE).
- Review staged files for secrets, private identifiers, incident data and local paths.
- Enable branch protection, required checks, CODEOWNERS, secret scanning where
  available, and a protected environment for any future deployment.
- Never upload the incident database, credentials, Terraform state, or kubeconfig.

The generated Terraform resource needs operator-selected provider account/region,
review of existing state/import requirements, and independently controlled execution.
It submits a quota request; AWS approval and actual EC2 capacity are separate concerns.

## License

Licensed under the [MIT License](LICENSE), copyright 2026 sanapleinc.
