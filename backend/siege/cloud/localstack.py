"""
LocalStack Pro backend (PRD FR-1.2 .. FR-1.6).

Requires LOCALSTACK_AUTH_TOKEN and ENFORCE_IAM=1 -- see docker-compose.yml.
ENFORCE_IAM is what makes the L1 permission layer real rather than simulated.
"""

from __future__ import annotations

import json
import time
from typing import Any

import boto3
import httpx
from botocore.config import Config
from botocore.exceptions import ClientError

from ..config import settings
from .base import CloudBackend, Credential

# Errors LocalStack/AWS raise when a call is denied by policy.
IAM_DENY_CODES = {
    "AccessDenied",
    "AccessDeniedException",
    "UnauthorizedOperation",
    "AuthorizationError",
    "Client.UnauthorizedOperation",
}

_BOTO_CONFIG = Config(
    retries={"max_attempts": 2, "mode": "standard"},
    connect_timeout=10,
    read_timeout=30,
)


def is_iam_denial(exc: BaseException) -> tuple[bool, str]:
    """Return (denied, raw_aws_message). The raw message is shown in the UI."""
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        msg = exc.response.get("Error", {}).get("Message", str(exc))
        if code in IAM_DENY_CODES:
            return True, msg
        return False, f"{code}: {msg}" if code else msg
    return False, str(exc)


class LocalStackBackend(CloudBackend):
    name = "localstack-pro"

    ADMIN = Credential(
        id="__admin__",
        access_key_id="test",
        secret_access_key="test",
        is_granted=False,
    )

    def __init__(self, endpoint_url: str | None = None, region: str | None = None) -> None:
        self.endpoint_url = endpoint_url or settings.aws_endpoint_url
        self.region = region or settings.aws_default_region
        self._clients: dict[tuple[str, str], Any] = {}

    # ------------------------------------------------------------------ #
    # Health
    # ------------------------------------------------------------------ #

    def health(self) -> bool:
        try:
            r = httpx.get(f"{self.endpoint_url}/_localstack/health", timeout=5.0)
            return r.status_code == 200
        except Exception:
            return False

    def health_detail(self) -> dict[str, Any]:
        try:
            r = httpx.get(f"{self.endpoint_url}/_localstack/health", timeout=5.0)
            return r.json() if r.status_code == 200 else {}
        except Exception:
            return {}

    def enforce_iam_active(self) -> bool:
        """Empirically verify enforcement rather than trusting configuration.

        Creates a deliberately powerless identity and confirms a denied call is
        actually denied. If this returns False the L2 detectors still work, so
        callers warn and continue (PRD FR-2.5).
        """
        probe_id = f"siege-iamprobe-{int(time.time())}"
        cred: Credential | None = None
        try:
            cred = self.create_credential(
                probe_id,
                {
                    "Version": "2012-10-17",
                    "Statement": [
                        {"Effect": "Allow", "Action": ["sts:GetCallerIdentity"], "Resource": "*"}
                    ],
                },
            )
            time.sleep(0.5)  # let the policy propagate
            try:
                self.client("s3", cred).list_buckets()
            except ClientError as exc:
                denied, _ = is_iam_denial(exc)
                return denied
            return False
        except Exception:
            return False
        finally:
            if cred is not None:
                try:
                    self.delete_credential(cred)
                except Exception:
                    pass

    def reset(self) -> bool:
        """POST /_localstack/state/reset. Callers fall back to name prefixing."""
        try:
            r = httpx.post(f"{self.endpoint_url}/_localstack/state/reset", timeout=30.0)
            ok = r.status_code in (200, 204)
        except Exception:
            ok = False
        if ok:
            self._clients.clear()
        return ok

    # ------------------------------------------------------------------ #
    # Clients
    # ------------------------------------------------------------------ #

    def client(self, service: str, credential: Credential | None = None) -> Any:
        cred = credential or self.ADMIN
        key = (service, cred.access_key_id)
        if key not in self._clients:
            self._clients[key] = boto3.client(
                service,
                endpoint_url=self.endpoint_url,
                region_name=self.region,
                aws_access_key_id=cred.access_key_id,
                aws_secret_access_key=cred.secret_access_key,
                config=_BOTO_CONFIG,
            )
        return self._clients[key]

    # ------------------------------------------------------------------ #
    # Credentials
    # ------------------------------------------------------------------ #

    def create_credential(self, cred_id: str, policy: dict[str, Any]) -> Credential:
        iam = self.client("iam")
        user_name = f"siege-{cred_id}"
        try:
            iam.create_user(UserName=user_name)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") != "EntityAlreadyExists":
                raise
        iam.put_user_policy(
            UserName=user_name,
            PolicyName=f"{cred_id}-scope",
            PolicyDocument=json.dumps(policy),
        )
        key = iam.create_access_key(UserName=user_name)["AccessKey"]
        return Credential(
            id=cred_id,
            access_key_id=key["AccessKeyId"],
            secret_access_key=key["SecretAccessKey"],
            user_name=user_name,
        )

    def delete_credential(self, cred: Credential) -> None:
        if not cred.user_name:
            return
        iam = self.client("iam")
        for call, kwargs in (
            (iam.delete_access_key, {"UserName": cred.user_name, "AccessKeyId": cred.access_key_id}),
            (iam.delete_user_policy, {"UserName": cred.user_name, "PolicyName": f"{cred.id}-scope"}),
            (iam.delete_user, {"UserName": cred.user_name}),
        ):
            try:
                call(**kwargs)
            except Exception:
                pass
        self._clients = {k: v for k, v in self._clients.items() if k[1] != cred.access_key_id}
