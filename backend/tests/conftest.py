"""
In-memory fake sandbox so the whole pipeline can be tested without Docker.

It deliberately implements a small IAM evaluator, because the DENY -> escalate ->
ALLOW sequence is the product's central claim and must be regression-tested
offline rather than only on demo day.

This is a TEST DOUBLE, not a second production backend (PRD decision D-4).
"""

from __future__ import annotations

import fnmatch
import itertools
from typing import Any

import pytest
from botocore.exceptions import ClientError

from siege.cloud.base import CloudBackend, Credential

_counter = itertools.count(1)


def _denied(action: str, user: str) -> ClientError:
    return ClientError(
        {"Error": {"Code": "AccessDenied",
                   "Message": (f"User: arn:aws:iam::000000000000:user/{user} is not authorized "
                               f"to perform: {action} because no identity-based policy allows "
                               f"the {action} action")}},
        action.split(":")[-1],
    )


def _policy_allows(policy: dict[str, Any], action: str, resource: str) -> bool:
    for stmt in policy.get("Statement", []):
        if stmt.get("Effect") != "Allow":
            continue
        actions = stmt.get("Action", [])
        actions = [actions] if isinstance(actions, str) else actions
        if not any(fnmatch.fnmatch(action, a) for a in actions):
            continue
        resources = stmt.get("Resource", ["*"])
        resources = [resources] if isinstance(resources, str) else resources
        if any(r == "*" or fnmatch.fnmatch(resource, r) or fnmatch.fnmatch(f"arn:aws:s3:::{resource}", r)
               for r in resources):
            return True
    return False


class _State:
    def __init__(self) -> None:
        self.buckets: dict[str, dict[str, str]] = {}
        self.secrets: dict[str, str] = {}
        self.params: dict[str, str] = {}
        self.dbs: dict[str, dict[str, Any]] = {}
        self.snapshots: dict[str, str] = {}
        self.instances: dict[str, dict[str, Any]] = {}
        self.log_groups: dict[str, list[str]] = {}


class _Client:
    """Implements just enough of each boto3 client, with IAM enforcement."""

    def __init__(self, service: str, state: _State, policy: dict | None, user: str) -> None:
        self.s, self.state, self.policy, self.user = service, state, policy, user

    def _guard(self, action: str, resource: str = "*") -> None:
        if self.policy is not None and not _policy_allows(self.policy, action, resource):
            raise _denied(action, self.user)

    # ---- s3 ---- #
    def create_bucket(self, Bucket, **k): self.state.buckets.setdefault(Bucket, {}); return {}
    def list_buckets(self, **k):
        self._guard("s3:ListAllMyBuckets")
        return {"Buckets": [{"Name": b} for b in self.state.buckets]}
    def put_object(self, Bucket, Key, Body=b"", **k):
        self._guard("s3:PutObject", Bucket)
        self.state.buckets.setdefault(Bucket, {})[Key] = (
            Body.decode() if isinstance(Body, bytes) else str(Body)); return {}
    def get_object(self, Bucket, Key, **k):
        self._guard("s3:GetObject", Bucket)
        import io
        return {"Body": io.BytesIO(self.state.buckets.get(Bucket, {}).get(Key, "").encode())}
    def list_objects_v2(self, Bucket, Prefix="", **k):
        self._guard("s3:ListBucket", Bucket)
        items = self.state.buckets.get(Bucket, {})
        return {"Contents": [{"Key": key, "Size": len(v)} for key, v in items.items()
                             if key.startswith(Prefix)]}
    def delete_object(self, Bucket, Key, **k):
        self._guard("s3:DeleteObject", Bucket)
        self.state.buckets.get(Bucket, {}).pop(Key, None); return {}
    def delete_bucket(self, Bucket, **k):
        self._guard("s3:DeleteBucket", Bucket)
        self.state.buckets.pop(Bucket, None); return {}

    # ---- secretsmanager ---- #
    def create_secret(self, Name, SecretString, **k): self.state.secrets[Name] = SecretString; return {}
    def put_secret_value(self, SecretId, SecretString, **k):
        self._guard("secretsmanager:PutSecretValue",
                    f"arn:aws:secretsmanager:us-east-1:000000000000:secret:{SecretId}")
        self.state.secrets[SecretId] = SecretString; return {"Name": SecretId}
    def list_secrets(self, **k):
        self._guard("secretsmanager:ListSecrets")
        return {"SecretList": [{"Name": n} for n in self.state.secrets]}
    def get_secret_value(self, SecretId, **k):
        self._guard("secretsmanager:GetSecretValue", SecretId)
        return {"Name": SecretId, "SecretString": self.state.secrets.get(SecretId, "")}

    # ---- ssm ---- #
    def put_parameter(self, Name, Value, **k): self.state.params[Name] = Value; return {}
    def get_parameter(self, Name, **k):
        self._guard("ssm:GetParameter", Name)
        return {"Parameter": {"Name": Name, "Value": self.state.params.get(Name, "")}}

    # ---- rds ---- #
    def create_db_instance(self, DBInstanceIdentifier, Tags=(), **k):
        self.state.dbs[DBInstanceIdentifier] = {
            "DBInstanceIdentifier": DBInstanceIdentifier, "Engine": k.get("Engine", "postgres"),
            "DBInstanceStatus": "available",
            "DBInstanceArn": f"arn:aws:rds:::db:{DBInstanceIdentifier}",
            "Tags": {t["Key"]: t["Value"] for t in Tags}}
        return {}
    def create_db_snapshot(self, DBSnapshotIdentifier, DBInstanceIdentifier, **k):
        self.state.snapshots[DBSnapshotIdentifier] = DBInstanceIdentifier; return {}
    def describe_db_instances(self, **k):
        self._guard("rds:DescribeDBInstances")
        return {"DBInstances": list(self.state.dbs.values())}
    def list_tags_for_resource(self, ResourceName, **k):
        ident = ResourceName.split(":")[-1]
        tags = self.state.dbs.get(ident, {}).get("Tags", {})
        return {"TagList": [{"Key": a, "Value": b} for a, b in tags.items()]}
    def describe_db_snapshots(self, DBInstanceIdentifier=None, **k):
        self._guard("rds:DescribeDBSnapshots")
        return {"DBSnapshots": [{"DBSnapshotIdentifier": s, "DBInstanceIdentifier": d,
                                 "Status": "available"}
                                for s, d in self.state.snapshots.items()
                                if not DBInstanceIdentifier or d == DBInstanceIdentifier]}
    def delete_db_instance(self, DBInstanceIdentifier, SkipFinalSnapshot=False, **k):
        self._guard("rds:DeleteDBInstance", DBInstanceIdentifier)
        self.state.dbs.pop(DBInstanceIdentifier, None)
        if not SkipFinalSnapshot:
            self.state.snapshots[f"{DBInstanceIdentifier}-final"] = DBInstanceIdentifier
        return {}
    def delete_db_snapshot(self, DBSnapshotIdentifier, **k):
        self._guard("rds:DeleteDBSnapshot", DBSnapshotIdentifier)
        self.state.snapshots.pop(DBSnapshotIdentifier, None); return {}

    # ---- ec2 ---- #
    def run_instances(self, InstanceType="t3.micro", MinCount=1, MaxCount=1,
                      TagSpecifications=(), **k):
        self._guard("ec2:RunInstances", InstanceType)
        tags = {}
        for spec in TagSpecifications or []:
            tags.update({t["Key"]: t["Value"] for t in spec.get("Tags", [])})
        made = []
        for _ in range(MinCount):
            iid = f"i-{next(_counter):08x}"
            self.state.instances[iid] = {"InstanceId": iid, "InstanceType": InstanceType,
                                         "State": {"Name": "running"},
                                         "Tags": [{"Key": a, "Value": b} for a, b in tags.items()]}
            made.append({"InstanceId": iid})
        return {"Instances": made}
    def describe_instances(self, **k):
        self._guard("ec2:DescribeInstances")
        return {"Reservations": [{"Instances": list(self.state.instances.values())}]}
    def terminate_instances(self, InstanceIds, **k):
        for iid in InstanceIds:
            self._guard("ec2:TerminateInstances", iid)
            self.state.instances.pop(iid, None)
        return {}

    # ---- logs ---- #
    def create_log_group(self, logGroupName, **k):
        self.state.log_groups.setdefault(logGroupName, []); return {}
    def create_log_stream(self, **k): return {}
    def put_log_events(self, logGroupName, logEvents, **k):
        self.state.log_groups.setdefault(logGroupName, []).extend(
            e["message"] for e in logEvents); return {}
    def describe_log_groups(self, **k):
        self._guard("logs:DescribeLogGroups")
        return {"logGroups": [{"logGroupName": n} for n in self.state.log_groups]}
    def describe_log_streams(self, logGroupName, **k):
        return {"logStreams": [{"logStreamName": "s1"}]}
    def get_log_events(self, logGroupName, limit=50, **k):
        self._guard("logs:GetLogEvents", logGroupName)
        return {"events": [{"message": m} for m in self.state.log_groups.get(logGroupName, [])[:limit]]}

    # ---- iam ---- #
    def create_user(self, **k): return {}
    def put_user_policy(self, **k): return {}
    def delete_access_key(self, **k): return {}
    def delete_user_policy(self, **k): return {}
    def delete_user(self, **k): return {}


class FakeBackend(CloudBackend):
    name = "fake-inmemory"

    def __init__(self) -> None:
        self.state = _State()
        self.policies: dict[str, dict] = {}     # access_key_id -> policy
        self.users: dict[str, str] = {}         # access_key_id -> user name

    def health(self) -> bool: return True
    def enforce_iam_active(self) -> bool: return True
    def reset(self) -> bool: self.state = _State(); return True

    def client(self, service: str, credential: Credential | None = None):
        policy = self.policies.get(credential.access_key_id) if credential else None
        user = self.users.get(credential.access_key_id, "admin") if credential else "admin"
        return _Client(service, self.state, policy, user)

    def create_credential(self, cred_id: str, policy: dict) -> Credential:
        key = f"AKIA{next(_counter):012d}"
        self.policies[key] = policy
        self.users[key] = f"siege-{cred_id}"
        return Credential(id=cred_id, access_key_id=key, secret_access_key="secret",
                          user_name=f"siege-{cred_id}")

    def delete_credential(self, cred: Credential) -> None:
        self.policies.pop(cred.access_key_id, None)
        self.users.pop(cred.access_key_id, None)


@pytest.fixture(autouse=True)
def isolated_runs_dir(tmp_path, monkeypatch):
    """Keep test artefacts out of the real runs/ directory."""
    import siege.config as config
    import siege.events as events
    import siege.orchestrator as orchestrator
    d = tmp_path / "runs"
    d.mkdir()
    monkeypatch.setattr(config, "RUNS_DIR", d)
    monkeypatch.setattr(events, "RUNS_DIR", d)
    monkeypatch.setattr(orchestrator, "RUNS_DIR", d)
    return d


@pytest.fixture
def backend() -> FakeBackend:
    return FakeBackend()
