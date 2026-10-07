import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from .core import Evidence, PlatformError, diagnose, parse_time, proposal


def canonical(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


class Store:
    def __init__(self, path: Path):
        self.connection = sqlite3.connect(path, timeout=5)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS incidents (
                incident_id TEXT PRIMARY KEY,
                evidence TEXT NOT NULL,
                diagnosis TEXT NOT NULL,
                status TEXT NOT NULL,
                target INTEGER,
                latest_observed_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                incident_id TEXT NOT NULL REFERENCES incidents(incident_id),
                occurred_at TEXT NOT NULL,
                event TEXT NOT NULL,
                details TEXT NOT NULL
            );
            """
        )

    def __enter__(self) -> "Store":
        return self

    def __exit__(self, *args: Any) -> None:
        self.connection.close()

    def _event(self, incident_id: str, event: str, details: Dict[str, Any]) -> None:
        self.connection.execute(
            "INSERT INTO audit (incident_id, occurred_at, event, details) VALUES (?, ?, ?, ?)",
            (incident_id, datetime.now(timezone.utc).isoformat(), event, canonical(details)),
        )

    def _row(self, incident_id: str) -> sqlite3.Row:
        row = self.connection.execute(
            "SELECT * FROM incidents WHERE incident_id = ?", (incident_id,)
        ).fetchone()
        if row is None:
            raise PlatformError("Unknown incident")
        return row

    def get(self, incident_id: str) -> Dict[str, Any]:
        row = self._row(incident_id)
        return {
            "incident_id": row["incident_id"],
            "status": row["status"],
            "target_vcpus": row["target"],
            "diagnosis": json.loads(row["diagnosis"]),
        }

    def investigate(self, evidence: Evidence) -> Dict[str, Any]:
        incident_id = hashlib.sha256(canonical(evidence.scope()).encode()).hexdigest()[:24]
        payload = canonical(evidence.payload())
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            existing = self.connection.execute(
                "SELECT evidence FROM incidents WHERE incident_id = ?", (incident_id,)
            ).fetchone()
            if existing:
                if existing["evidence"] != payload:
                    raise PlatformError("Incident key already exists with different evidence; use a new key")
            else:
                result = diagnose(evidence)
                self.connection.execute(
                    "INSERT INTO incidents VALUES (?, ?, ?, ?, ?, ?)",
                    (incident_id, payload, canonical(result), "investigated", None, evidence.observed_at),
                )
                self._event(incident_id, "investigated", result)
        return self.get(incident_id)

    def propose(self, incident_id: str, target: int, now: Optional[datetime] = None) -> str:
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self._row(incident_id)
            if row["status"] not in {"investigated", "proposal_ready"}:
                raise PlatformError("Proposal cannot change after recovery verification has started")
            evidence = Evidence.parse(
                json.loads(row["evidence"]),
                now or datetime.now(timezone.utc),
            )
            text = proposal(evidence, target)
            if row["status"] == "proposal_ready":
                if row["target"] != target:
                    raise PlatformError("Existing proposal target differs; create a new investigation")
                return text
            self.connection.execute(
                "UPDATE incidents SET status = ?, target = ? WHERE incident_id = ?",
                ("proposal_ready", target, incident_id),
            )
            self._event(incident_id, "proposal_ready", {"target_vcpus": target})
        return text

    def verify(self, incident_id: str, evidence: Evidence) -> Dict[str, Any]:
        with self.connection:
            self.connection.execute("BEGIN IMMEDIATE")
            row = self._row(incident_id)
            if row["status"] not in {"proposal_ready", "awaiting_recovery"}:
                raise PlatformError("Verification requires an open proposal")
            original = json.loads(row["evidence"])
            if evidence.scope() != tuple(original[key] for key in (
                "incident_key", "account_id", "region", "cluster", "quota_code",
            )):
                raise PlatformError("Recovery evidence must match the original incident scope")
            timestamp = parse_time(evidence.observed_at)
            if timestamp < parse_time(row["latest_observed_at"]):
                raise PlatformError("Recovery evidence predates the latest observation")
            checks = {
                "new_observation": timestamp > parse_time(original["observed_at"]),
                "effective_quota": evidence.quota_vcpus >= row["target"],
                "successful_launches": evidence.successful_launches > 0,
                "pending_pods_cleared": evidence.pending_pods == 0,
                "nodeclaims_healthy": evidence.failed_nodeclaims == 0,
                "launch_errors_cleared": evidence.launch_error == "None",
                "application_healthy": evidence.application_healthy,
            }
            status = "recovered" if all(checks.values()) else "awaiting_recovery"
            self.connection.execute(
                "UPDATE incidents SET status = ?, latest_observed_at = ? WHERE incident_id = ?",
                (status, evidence.observed_at, incident_id),
            )
            self._event(incident_id, status, {
                "checks": checks,
                "evidence_sha256": hashlib.sha256(canonical(evidence.payload()).encode()).hexdigest(),
                "observed_at": evidence.observed_at,
            })
        return dict(self.get(incident_id), checks=checks)

    def audit(self, incident_id: str) -> list:
        self._row(incident_id)
        return [
            dict(row, details=json.loads(row["details"]))
            for row in self.connection.execute(
                "SELECT * FROM audit WHERE incident_id = ? ORDER BY sequence", (incident_id,)
            )
        ]
