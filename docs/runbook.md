# Manual fallback: EKS provisioning failure

This runbook must remain usable without an agent. The current project does not run
these checks against a cluster; operators use their existing authorized tooling.

1. Confirm affected account, region, cluster, incident time and application impact.
2. Inspect Pending pod scheduling events. Separate affinity, taints, storage and
   resource-request constraints from missing node capacity.
3. Inspect Karpenter NodeClaims, NodePools and provisioning failures.
4. Correlate EC2 CreateFleet/RunInstances failures and relevant CloudTrail events.
   An IAM denial and insufficient regional capacity require different remediation.
5. Check the **correct quota bucket**: Standard versus other instance families,
   On-Demand versus Spot, and the intended AWS region. This demonstrator supports
   Standard On-Demand vCPUs (`L-1216C47A`) only.
6. Compare effective quota, current regional usage and requested additional capacity.
   Pending pods alone are not evidence of quota exhaustion.
7. If a quota increase is warranted, review headroom, cost controls, repository
   ownership, Terraform provider region/account, and existing managed/imported state.
8. Submit through the approved human-controlled path. Record request ID and approval
   status; set a deadline and escalate if delayed or denied. Do not repeatedly submit.
9. Verify the effective quota changed, instances launched, pods scheduled and
   application health/SLOs recovered over a stability window.
10. Record evidence, decisions, timestamps, reviewers and follow-up prevention work.

Quota increases are not reliably reversible mitigation. If approval is delayed,
consider explicitly reviewed capacity/scheduling alternatives; do not automatically
relax security controls, evict workloads, change instance types, or expand regions.

Prevent recurrence with quota-headroom alerting, capacity forecasts and separately
tested monitoring. AI failure should not stop notification, investigation or recovery.
