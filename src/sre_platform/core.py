import re
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Dict


class PlatformError(ValueError):
    """An explicit input, evidence, or policy failure."""


QUOTA_CODE = "L-1216C47A"
ERROR_CODES = {
    "VcpuLimitExceeded", "InstanceLimitExceeded", "UnauthorizedOperation",
    "InsufficientInstanceCapacity", "Unknown", "None",
}


@dataclass(frozen=True)
class Evidence:
    incident_key: str
    account_id: str
    region: str
    cluster: str
    observed_at: str
    quota_code: str
    quota_vcpus: int
    used_vcpus: int
    pending_pods: int
    failed_nodeclaims: int
    launch_error: str
    successful_launches: int
    application_healthy: bool

    @classmethod
    def parse(cls, value: Any, now: datetime) -> "Evidence":
        fields = set(cls.__dataclass_fields__)
        if not isinstance(value, dict) or set(value) != fields:
            raise PlatformError("Evidence must contain exactly the documented schema fields")
        patterns = {
            "incident_key": r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,79}",
            "account_id": r"[0-9]{12}",
            "region": r"[a-z]{2}(?:-[a-z]+){1,2}-[0-9]",
            "cluster": r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,99}",
        }
        for field, pattern in patterns.items():
            if not isinstance(value[field], str) or not re.fullmatch(pattern, value[field]):
                raise PlatformError(f"Invalid {field}")
        for field in (
            "quota_vcpus", "used_vcpus", "pending_pods",
            "failed_nodeclaims", "successful_launches",
        ):
            number = value[field]
            minimum = 1 if field == "quota_vcpus" else 0
            if type(number) is not int or not minimum <= number <= 1_000_000:
                raise PlatformError(f"{field} must be an integer between {minimum} and 1000000")
        if value["quota_code"] != QUOTA_CODE:
            raise PlatformError("Only the Standard On-Demand EC2 vCPU quota is supported")
        if not isinstance(value["launch_error"], str) or value["launch_error"] not in ERROR_CODES:
            raise PlatformError("Unsupported launch_error; free-text logs are not accepted")
        if type(value["application_healthy"]) is not bool:
            raise PlatformError("application_healthy must be a boolean")
        timestamp = parse_time(value["observed_at"])
        if now.tzinfo is None or not timedelta(0) <= now - timestamp <= timedelta(minutes=15):
            raise PlatformError("Evidence must be timezone-aware, not future-dated, and at most 15 minutes old")
        return cls(**value)

    def payload(self) -> Dict[str, Any]:
        return asdict(self)

    def scope(self) -> tuple:
        return self.incident_key, self.account_id, self.region, self.cluster, self.quota_code


def parse_time(value: Any) -> datetime:
    if not isinstance(value, str) or len(value) > 40:
        raise PlatformError("Invalid observed_at timestamp")
    try:
        timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise PlatformError("Invalid observed_at timestamp") from exc
    if timestamp.tzinfo is None:
        raise PlatformError("observed_at requires a timezone")
    return timestamp.astimezone(timezone.utc)


def diagnose(evidence: Evidence) -> Dict[str, Any]:
    supported = (
        evidence.pending_pods > 0
        and evidence.failed_nodeclaims > 0
        and evidence.launch_error in {"VcpuLimitExceeded", "InstanceLimitExceeded"}
        and evidence.used_vcpus >= evidence.quota_vcpus
    )
    return {
        "cause": "ec2_vcpu_quota_exhausted" if supported else "undetermined",
        "evidence_ids": [
            "pending_pods", "failed_nodeclaims", "launch_error",
            "used_vcpus", "quota_vcpus",
        ] if supported else [],
        "summary": (
            "Scoped synthetic signals support EC2 vCPU quota exhaustion. "
            "A quota increase request requires human review and AWS approval."
            if supported else
            "Evidence does not establish quota exhaustion. Inspect IAM, EC2 capacity, "
            "Karpenter constraints, and scheduling events using the manual runbook."
        ),
    }


def proposal(evidence: Evidence, target: int) -> str:
    if diagnose(evidence)["cause"] != "ec2_vcpu_quota_exhausted":
        raise PlatformError("A quota proposal requires an evidence-backed quota diagnosis")
    maximum = min(evidence.quota_vcpus * 2, 1024)
    if type(target) is not int or not evidence.quota_vcpus < target <= maximum:
        raise PlatformError(f"Target must exceed current quota and be at most {maximum} vCPUs")
    return (
        "# PROPOSAL ONLY: review account, region, existing state and costs before use.\n"
        "# Applying requests an increase; it does not guarantee approval or EC2 capacity.\n"
        'resource "aws_servicequotas_service_quota" "standard_ondemand_vcpus" {\n'
        '  service_code = "ec2"\n'
        f'  quota_code   = "{QUOTA_CODE}"\n'
        f"  value        = {target}\n"
        "}\n"
    )


def validate_explanation(value: Any, result: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(value, dict) or set(value) != {"cause", "evidence_ids", "summary"}:
        raise PlatformError("Explanation requires exactly cause, evidence_ids, and summary")
    if value["cause"] != result["cause"]:
        raise PlatformError("Explanation cannot override the deterministic diagnosis")
    ids = value["evidence_ids"]
    if (
        not isinstance(ids, list)
        or not all(isinstance(item, str) for item in ids)
        or len(ids) != len(set(ids))
        or set(ids) != set(result["evidence_ids"])
    ):
        raise PlatformError("Explanation must reference exactly the established evidence IDs")
    summary = value["summary"]
    if not isinstance(summary, str) or not 1 <= len(summary.strip()) <= 1000:
        raise PlatformError("Explanation summary must be between 1 and 1000 characters")
    if any(ord(char) < 32 for char in summary) or re.search(
        r"AKIA[0-9A-Z]{16}|ASIA[0-9A-Z]{16}|-----BEGIN|"
        r"(?i:password|secret|token|api[_-]?key)\s*[:=]",
        summary,
    ):
        raise PlatformError("Explanation contains control characters or a potential credential")
    return value
