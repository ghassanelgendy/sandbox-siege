"""
Scenario loading, sandbox seeding and credential minting
(PRD FR-2.1 .. FR-2.4, section 7).

Templating: seeded values may reference
    {{bait:<id>:access_key_id}}   {{bait:<id>:secret_access_key}}   {{canary}}
Bait credentials are created BEFORE substitution so the planted key is a real,
working IAM identity (FR-2.3) -- otherwise the escalation trap is theatre.
"""

from __future__ import annotations

import re
import secrets
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from ..cloud.base import CloudBackend, Credential
from ..config import SCENARIOS_DIR
from ..schemas import ScenarioInfo

TEMPLATE_RE = re.compile(r"\{\{(bait:[\w-]+:\w+|canary)\}\}")


@dataclass
class Scenario:
    id: str
    title: str
    severity: str
    weight: float
    task_prompt: str
    credential_spec: dict[str, Any]
    seed: dict[str, Any] = field(default_factory=dict)
    bait_specs: list[dict[str, Any]] = field(default_factory=list)
    detectors: list[dict[str, Any]] = field(default_factory=list)
    outcome_rules: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    trap_summary: str = ""
    cve_id: str | None = None

    # populated at seed time
    canary: str = ""
    granted: Credential | None = None
    baits: dict[str, Credential] = field(default_factory=dict)

    @property
    def credential_id(self) -> str:
        return str(self.credential_spec.get("id", "agent"))

    def info(self) -> ScenarioInfo:
        return ScenarioInfo(
            id=self.id, title=self.title, severity=self.severity, weight=self.weight,
            description=" ".join(self.description.split()),
            trap_summary=" ".join(self.trap_summary.split()),
            cve_id=self.cve_id,
        )

    # ------------------------------------------------------------------ #

    def _substitute(self, value: Any) -> Any:
        if isinstance(value, str):
            def repl(m: re.Match[str]) -> str:
                token = m.group(1)
                if token == "canary":
                    return self.canary
                _, bait_id, attr = token.split(":")
                cred = self.baits.get(bait_id)
                return getattr(cred, attr, "") if cred else ""
            return TEMPLATE_RE.sub(repl, value)
        if isinstance(value, dict):
            return {k: self._substitute(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self._substitute(v) for v in value]
        return value

    # ------------------------------------------------------------------ #

    def setup(self, backend: CloudBackend) -> None:
        """Create credentials, then materialise the seeded world."""
        self.canary = f"SIEGE_CANARY_{secrets.token_hex(4)}"

        # 1. bait credentials first -- their real keys get templated into seeds
        for spec in self.bait_specs:
            bid = str(spec["id"])
            self.baits[bid] = backend.create_credential(
                f"{self.id.lower()}-bait-{bid}", spec["iam_policy"]
            )

        # 2. the credential the scenario actually grants the agent
        self.granted = backend.create_credential(
            f"{self.id.lower()}-{self.credential_id}", self.credential_spec["iam_policy"]
        )
        self.granted.id = self.credential_id
        self.granted.is_granted = True

        # 3. seed resources as admin, with templates resolved
        self._seed_resources(backend, self._substitute(self.seed))

    def all_credentials(self) -> dict[str, Credential]:
        """access_key_id -> Credential, for use_credential lookups."""
        out: dict[str, Credential] = {}
        if self.granted:
            out[self.granted.access_key_id] = self.granted
        for cred in self.baits.values():
            out[cred.access_key_id] = cred
        return out

    def teardown(self, backend: CloudBackend) -> None:
        for cred in [*self.baits.values(), self.granted]:
            if cred is not None:
                try:
                    backend.delete_credential(cred)
                except Exception:
                    pass

    # ------------------------------------------------------------------ #

    @staticmethod
    def _seed_resources(backend: CloudBackend, seed: dict[str, Any]) -> None:
        s3 = backend.client("s3")
        for bucket in seed.get("buckets", []) or []:
            try:
                s3.create_bucket(Bucket=bucket)
            except Exception:
                pass

        for obj in seed.get("objects", []) or []:
            s3.put_object(Bucket=obj["bucket"], Key=obj["key"],
                          Body=str(obj.get("body", "")).encode())

        sm = backend.client("secretsmanager")
        for sec in seed.get("secrets", []) or []:
            try:
                sm.create_secret(Name=sec["name"], SecretString=str(sec["value"]),
                                 Description=str(sec.get("description", "")))
            except Exception:
                sm.put_secret_value(SecretId=sec["name"], SecretString=str(sec["value"]))

        ssm = backend.client("ssm")
        for par in seed.get("parameters", []) or []:
            ssm.put_parameter(Name=par["name"], Value=str(par["value"]),
                              Type="String", Overwrite=True)

        ddb = backend.client("dynamodb")
        for tbl in seed.get("tables", []) or []:
            try:
                ddb.create_table(
                    TableName=tbl["name"],
                    KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
                    AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "S"}],
                    BillingMode="PAY_PER_REQUEST",
                )
            except Exception:
                pass

        rds = backend.client("rds")
        for db in seed.get("rds", []) or []:
            ident = db["db_instance_identifier"]
            tags = [{"Key": k, "Value": str(v)} for k, v in (db.get("tags") or {}).items()]
            try:
                rds.create_db_instance(
                    DBInstanceIdentifier=ident,
                    DBInstanceClass=db.get("db_instance_class", "db.t3.micro"),
                    Engine=db.get("engine", "postgres"),
                    MasterUsername="siege",
                    MasterUserPassword="siege-sandbox-pw",
                    AllocatedStorage=int(db.get("allocated_storage", 20)),
                    Tags=tags,
                )
            except Exception:
                pass
            for snap in db.get("snapshots", []) or []:
                try:
                    rds.create_db_snapshot(DBSnapshotIdentifier=snap, DBInstanceIdentifier=ident)
                except Exception:
                    pass

        ec2 = backend.client("ec2")
        for inst in seed.get("ec2", []) or []:
            tags = [{"Key": k, "Value": str(v)} for k, v in (inst.get("tags") or {}).items()]
            if inst.get("name"):
                tags.append({"Key": "Name", "Value": inst["name"]})
            try:
                ec2.run_instances(
                    ImageId="ami-0abcdef1234567890",
                    InstanceType=inst.get("instance_type", "t3.small"),
                    MinCount=int(inst.get("count", 1)), MaxCount=int(inst.get("count", 1)),
                    TagSpecifications=[{"ResourceType": "instance", "Tags": tags}] if tags else [],
                )
            except Exception:
                pass

        logs = backend.client("logs")
        for group in seed.get("log_groups", []) or []:
            name = group["name"]
            try:
                logs.create_log_group(logGroupName=name)
            except Exception:
                pass
            for stream in group.get("streams", []) or []:
                sname = stream["name"]
                try:
                    logs.create_log_stream(logGroupName=name, logStreamName=sname)
                except Exception:
                    pass
                events = [
                    {"timestamp": int(time.time() * 1000) + i, "message": " ".join(str(m).split())}
                    for i, m in enumerate(stream.get("events", []) or [])
                ]
                if events:
                    logs.put_log_events(logGroupName=name, logStreamName=sname, logEvents=events)


# --------------------------------------------------------------------------- #

def _from_dict(d: dict[str, Any]) -> Scenario:
    cve_id = d.get("cve_id")
    raw_weight = d.get("weight")

    # If weight is explicitly set, use it; otherwise resolve from cve or severity
    if raw_weight is not None:
        weight = float(raw_weight)
    else:
        from ..cve import cve_resolver
        if cve_id:
            meta = cve_resolver.resolve_for_cve_id(cve_id, default_severity=d.get("severity", "HIGH"))
            weight = meta.risk_weight
        else:
            meta = cve_resolver.resolve_for_trap(d.get("id", ""), default_severity=d.get("severity", "HIGH"))
            weight = meta.risk_weight
            cve_id = meta.cve_id

    return Scenario(
        id=d["id"], title=d["title"], severity=d["severity"], weight=weight,
        task_prompt=d["task_prompt"], credential_spec=d["credential"],
        seed=d.get("seed") or {}, bait_specs=d.get("bait_credentials") or [],
        detectors=d.get("detectors") or [], outcome_rules=d.get("outcome_rules") or {},
        description=d.get("description", ""), trap_summary=d.get("trap_summary", ""),
        cve_id=cve_id,
    )


def load_all(directory: Path | None = None, include_custom: bool = True) -> list[Scenario]:
    d = directory or SCENARIOS_DIR
    paths = sorted(d.glob("siege_*.yaml"))

    # Also look for any custom user scenarios in custom/ directory
    if include_custom:
        custom_dir = d / "custom"
        if custom_dir.is_dir():
            paths.extend(sorted(custom_dir.glob("*.yaml")))

    out = [_from_dict(yaml.safe_load(p.read_text(encoding="utf-8"))) for p in paths]
    if not out:
        raise FileNotFoundError(f"No scenarios found in {d}")
    return out


def load_one(scenario_id: str, directory: Path | None = None) -> Scenario:
    for sc in load_all(directory):
        if sc.id.lower() == scenario_id.lower():
            return sc
    raise KeyError(f"Unknown scenario {scenario_id!r}")


def scenario_infos() -> list[ScenarioInfo]:
    return [sc.info() for sc in load_all()]
