import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .core import Evidence, PlatformError, diagnose, validate_explanation
from .store import Store


def unique_object(pairs: list) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise PlatformError("Duplicate JSON keys are not allowed")
        result[key] = value
    return result


def load(path: Path) -> Any:
    with path.open("rb") as stream:
        content = stream.read(65537)
    if len(content) > 65536:
        raise PlatformError("Input exceeds 64 KiB")
    return json.loads(content, object_pairs_hook=unique_object)


def demo(store: Store, now: datetime) -> dict:
    initial = {
        "incident_key": "demo-" + now.strftime("%Y%m%dT%H%M%S%f"),
        "account_id": "000000000000", "region": "us-east-1", "cluster": "synthetic-eks",
        "observed_at": (now - timedelta(seconds=10)).isoformat(),
        "quota_code": "L-1216C47A", "quota_vcpus": 32, "used_vcpus": 32,
        "pending_pods": 8, "failed_nodeclaims": 2, "launch_error": "VcpuLimitExceeded",
        "successful_launches": 0, "application_healthy": False,
    }
    incident = store.investigate(Evidence.parse(initial, now))
    incident_id = incident["incident_id"]
    terraform = store.propose(incident_id, 64, now)
    waiting = store.verify(incident_id, Evidence.parse(initial, now))
    recovery = dict(
        initial, observed_at=now.isoformat(), quota_vcpus=64, pending_pods=0,
        failed_nodeclaims=0, launch_error="None", successful_launches=2,
        application_healthy=True,
    )
    recovered = store.verify(incident_id, Evidence.parse(recovery, now))
    return {
        "mode": "synthetic_offline",
        "investigation": incident,
        "terraform_proposal": terraform,
        "before_effective_increase": waiting,
        "simulated_recovery": recovered,
        "audit": store.audit(incident_id),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline evidence-backed SRE investigation")
    parser.add_argument("--db", type=Path, default=Path("incidents.db"))
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("demo")
    investigate = commands.add_parser("investigate")
    investigate.add_argument("evidence", type=Path)
    investigate.add_argument("--explanation", type=Path)
    propose = commands.add_parser("propose")
    propose.add_argument("incident_id")
    propose.add_argument("--target-vcpus", type=int, required=True)
    verify = commands.add_parser("verify")
    verify.add_argument("incident_id")
    verify.add_argument("evidence", type=Path)
    for command in ("show", "audit"):
        commands.add_parser(command).add_argument("incident_id")
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    try:
        # Validate input before opening or mutating the incident database.
        evidence = Evidence.parse(load(args.evidence), now) if args.command in {
            "investigate", "verify",
        } else None
        has_explanation = args.command == "investigate" and args.explanation is not None
        explanation = load(args.explanation) if has_explanation else None
        if has_explanation:
            if evidence is None:
                raise PlatformError("Explanation requires investigation evidence")
            validate_explanation(explanation, diagnose(evidence))
        with Store(args.db) as store:
            if args.command == "demo":
                output = demo(store, now)
            elif args.command == "investigate":
                if evidence is None:
                    raise PlatformError("Investigation requires evidence")
                output = store.investigate(evidence)
                if has_explanation:
                    output["untrusted_explanation"] = explanation
            elif args.command == "propose":
                output = {"terraform_proposal": store.propose(args.incident_id, args.target_vcpus, now)}
            elif args.command == "verify":
                if evidence is None:
                    raise PlatformError("Verification requires evidence")
                output = store.verify(args.incident_id, evidence)
            elif args.command == "audit":
                output = store.audit(args.incident_id)
            else:
                output = store.get(args.incident_id)
        print(json.dumps(output, indent=2, allow_nan=False))
        return 3 if args.command == "verify" and output["status"] != "recovered" else 0
    except (PlatformError, OSError, sqlite3.Error, UnicodeError, json.JSONDecodeError) as exc:
        print(json.dumps({"error": str(exc)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
