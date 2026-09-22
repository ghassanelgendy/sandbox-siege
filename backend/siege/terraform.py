"""
Terraform / OpenTofu HCL / YAML infra parser and LocalStack sandbox seeder.

Allows users to import their actual infrastructure declarations directly into
Sandbox Siege scenarios so that testing takes place against exact replicas of
production infrastructure rather than toy mocks.

Real-world Terraform is never made of pure literals: values reference `var.x`,
`local.x`, `data.x.y`, `module.x.y` or `${...}` interpolations, resource names use
underscores that AWS itself would reject for S3/RDS identifiers, numeric fields
sometimes carry unresolved expressions, and secrets/policies are often heredocs.
Anything unresolved or invalid must fall back to a safe literal *here* -- a value
that survives boto3 validation -- otherwise LocalStack rejects the create call and
the scenario silently runs against a resource that was never actually seeded.

Supported resource types are seeded into LocalStack AND get matching agent tools
(backend/siege/tools/registry.py) -- seeding something the agent has no tool to
touch would be inert. Anything else recognised as `aws_*` but not (yet) actionable
is reported via `unmapped` rather than silently dropped, so the trap suggester can
still surface it (PRD §8.3).
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any, NamedTuple
import yaml

logger = logging.getLogger("siege.terraform")

# Matches an unresolved Terraform expression: "${...}" interpolation, or a bare
# reference like "var.foo", "local.foo", "data.x.y", "module.x.y", "each.value",
# "count.index", "self.id".
_UNRESOLVED_RE = re.compile(r"\$\{|^(var|local|module|data|each|count|self)\.")

_HEREDOC_RE = re.compile(
    r'([\w-]+)\s*=\s*<<-?\s*"?(\w+)"?\s*\n([\s\S]*?)\n\s*\2\b', re.MULTILINE
)

# Native seed dict keys this parser can produce -- used to detect an
# already-native seed payload passed straight through (see parse_terraform_structure).
_NATIVE_SEED_KEYS = (
    "buckets", "rds", "ec2", "secrets", "tables", "log_groups",
    "iam_roles", "iam_policies", "kms_keys", "sns_topics", "sqs_queues", "security_groups",
)


class TerraformParseResult(NamedTuple):
    seed: dict[str, Any]
    unmapped: list[dict[str, str]]


def _resolved(value: Any, fallback: Any) -> Any:
    """Return `value` unless it's empty or an unresolved Terraform expression."""
    if value is None:
        return fallback
    s = str(value).strip()
    if not s or _UNRESOLVED_RE.search(s):
        return fallback
    return value


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return default


def _sanitize_bucket_name(name: str) -> str:
    """Coerce an arbitrary identifier into a valid S3 bucket name."""
    s = re.sub(r"[^a-z0-9.-]", "-", str(name).strip().lower())
    s = re.sub(r"-{2,}", "-", s).strip("-.")
    if not s:
        s = "siege-bucket"
    if len(s) < 3:
        s = f"siege-{s}"
    return s[:63]


def _sanitize_rds_identifier(name: str) -> str:
    """Coerce an arbitrary identifier into a valid RDS DB instance/cluster identifier
    (letters, digits, hyphens only; must start with a letter)."""
    s = re.sub(r"[^a-zA-Z0-9-]", "-", str(name).strip())
    s = re.sub(r"-{2,}", "-", s).strip("-")
    if not s or not s[0].isalpha():
        s = f"db-{s}" if s else "db-instance"
    return s[:63]


def _sanitize_name(name: Any, max_len: int = 64) -> str:
    """Generic AWS resource-name sanitizer (IAM role/policy, SNS topic, SQS queue,
    security group): alphanumerics, hyphen, underscore, period only."""
    s = re.sub(r"[^a-zA-Z0-9_.-]", "-", str(name).strip())
    s = re.sub(r"-{2,}", "-", s).strip("-")
    if not s:
        s = "siege-resource"
    return s[:max_len]


def _parse_policy_json(value: Any) -> dict[str, Any] | None:
    """Best-effort parse of an IAM policy/trust-policy attribute.

    Handles a literal JSON string or an already-parsed dict (native YAML input).
    Terraform's `jsonencode({...})` wraps an HCL object expression, not JSON, so
    it cannot be parsed without a full HCL evaluator -- that case (and any other
    unparseable expression) returns None and the caller substitutes a safe default
    rather than seeding a broken policy.
    """
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return None
    s = value.strip()
    if s.startswith("jsonencode(") and s.endswith(")"):
        s = s[len("jsonencode("):-1].strip()
    try:
        parsed = json.loads(s)
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


def _default_trust_policy() -> dict[str, Any]:
    return {
        "Version": "2012-10-17",
        "Statement": [{
            "Effect": "Allow",
            "Principal": {"Service": "ec2.amazonaws.com"},
            "Action": "sts:AssumeRole",
        }],
    }


def _default_iam_policy_document() -> dict[str, Any]:
    return {
        "Version": "2012-10-17",
        "Statement": [{"Effect": "Allow", "Action": ["s3:GetObject"], "Resource": "*"}],
    }


def parse_terraform_structure(raw_content: str) -> dict[str, Any]:
    """Parse Terraform declared resources in YAML, JSON, or HCL-like format into
    a Sandbox Siege seed dict. See `parse_terraform_full` for the variant that
    also reports resource types Siege can't yet seed/test."""
    return parse_terraform_full(raw_content).seed


def parse_terraform_full(raw_content: str) -> TerraformParseResult:
    content = raw_content.strip()
    if not content:
        return TerraformParseResult({}, [])

    # 1. Try direct YAML / JSON
    try:
        data = yaml.safe_load(content)
        if isinstance(data, dict):
            if "resource" in data:
                return _convert_tf_resource_dict(data["resource"])
            elif "terraform" in data and isinstance(data["terraform"], dict) and "resource" in data["terraform"]:
                return _convert_tf_resource_dict(data["terraform"]["resource"])
            elif any(k in data for k in _NATIVE_SEED_KEYS):
                # Already a native seed dict -- nothing to map, nothing unmapped.
                return TerraformParseResult(data, [])
            else:
                return _convert_tf_resource_dict(data)
    except Exception:
        pass

    # 2. Try HCL block regex parsing (simple fallback for resource "aws_..." "name" { ... })
    return _parse_simple_hcl(content)


def _convert_tf_resource_dict(resources: dict[str, Any]) -> TerraformParseResult:
    """Convert parsed Terraform resource definitions to the Sandbox Siege seed schema."""
    seed: dict[str, Any] = {
        "buckets": [], "objects": [], "secrets": [], "parameters": [], "tables": [],
        "rds": [], "ec2": [], "log_groups": [],
        "iam_roles": [], "iam_policies": [], "kms_keys": [], "sns_topics": [],
        "sqs_queues": [], "security_groups": [],
    }
    unmapped: list[dict[str, str]] = []

    for res_type, instances in resources.items():
        if not isinstance(instances, dict):
            continue

        # S3 Buckets
        if res_type in ("aws_s3_bucket", "s3_bucket", "s3"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                bucket_name = _resolved(props.get("bucket"), res_name)
                seed["buckets"].append(_sanitize_bucket_name(bucket_name))

        # S3 Objects
        elif res_type in ("aws_s3_object", "aws_s3_bucket_object", "s3_object"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                bucket = _resolved(props.get("bucket"), "default-bucket")
                seed["objects"].append({
                    "bucket": _sanitize_bucket_name(bucket),
                    "key": _resolved(props.get("key"), res_name),
                    "body": _resolved(props.get("content"), _resolved(props.get("body"), "terraform-seeded-content")),
                })

        # RDS Instances
        elif res_type in ("aws_db_instance", "db_instance", "rds"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                ident_raw = _resolved(props.get("identifier"), _resolved(props.get("db_instance_identifier"), res_name))
                ident = _sanitize_rds_identifier(ident_raw)
                tags = props.get("tags") or {}
                if not isinstance(tags, dict):
                    tags = {}
                engine = str(_resolved(props.get("engine"), "postgres")).lower()
                storage = _safe_int(_resolved(props.get("allocated_storage"), 20), 20)
                snapshots_raw = props.get("snapshots")
                snapshots = snapshots_raw if isinstance(snapshots_raw, list) and snapshots_raw else [f"{ident}-snap-latest"]
                seed["rds"].append({
                    "db_instance_identifier": ident,
                    "engine": engine,
                    "db_instance_class": _resolved(
                        props.get("instance_class"), _resolved(props.get("db_instance_class"), "db.t3.micro")
                    ),
                    "allocated_storage": storage,
                    "tags": tags,
                    "snapshots": [_sanitize_rds_identifier(s) for s in snapshots],
                })

        # EC2 Instances
        elif res_type in ("aws_instance", "instance", "ec2"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                raw_tags = props.get("tags")
                tags = raw_tags if isinstance(raw_tags, dict) else {}
                seed["ec2"].append({
                    "name": tags.get("Name", res_name) if isinstance(tags, dict) else res_name,
                    "instance_type": _resolved(props.get("instance_type"), "t3.small"),
                    "count": _safe_int(_resolved(props.get("count"), 1), 1),
                    "tags": tags,
                })

        # Secrets Manager
        elif res_type in ("aws_secretsmanager_secret", "secretsmanager_secret", "secrets"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                seed["secrets"].append({
                    "name": _resolved(props.get("name"), res_name),
                    "description": _resolved(props.get("description"), "Terraform seeded secret"),
                    "value": _resolved(
                        props.get("secret_string"), _resolved(props.get("value"), '{"status":"active"}')
                    ),
                })

        # DynamoDB Tables
        elif res_type in ("aws_dynamodb_table", "dynamodb_table", "tables"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                seed["tables"].append({
                    "name": _resolved(props.get("name"), res_name),
                    "hash_key": _resolved(props.get("hash_key"), "id"),
                })

        # CloudWatch Log Groups
        elif res_type in ("aws_cloudwatch_log_group", "cloudwatch_log_group", "log_groups"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                seed["log_groups"].append({
                    "name": _resolved(props.get("name"), f"/aws/{res_name}"),
                    "streams": props.get("streams", [{"name": "app-stream", "events": ["[INFO] Infrastructure provisioned via Terraform."]}]),
                })

        # SSM Parameters (tool already exists: ssm_get_parameter)
        elif res_type in ("aws_ssm_parameter", "ssm_parameter"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                seed["parameters"].append({
                    "name": _resolved(props.get("name"), f"/{res_name}"),
                    "value": _resolved(props.get("value"), "terraform-seeded-value"),
                })

        # IAM Roles
        elif res_type in ("aws_iam_role", "iam_role"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                name = _sanitize_name(_resolved(props.get("name"), res_name), 64)
                trust = _parse_policy_json(props.get("assume_role_policy")) or _default_trust_policy()
                tags = props.get("tags") if isinstance(props.get("tags"), dict) else {}
                seed["iam_roles"].append({"name": name, "assume_role_policy": trust, "tags": tags})

        # IAM (managed) Policies
        elif res_type in ("aws_iam_policy", "iam_policy"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                name = _sanitize_name(_resolved(props.get("name"), res_name), 128)
                doc = _parse_policy_json(props.get("policy")) or _default_iam_policy_document()
                seed["iam_policies"].append({"name": name, "policy": doc})

        # KMS Keys
        elif res_type in ("aws_kms_key", "kms_key"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                alias = _sanitize_name(_resolved(props.get("description"), res_name), 60).lower()
                tags = props.get("tags") if isinstance(props.get("tags"), dict) else {}
                seed["kms_keys"].append({
                    "alias": f"alias/{alias}",
                    "description": _resolved(props.get("description"), "Terraform seeded key"),
                    "tags": tags,
                })

        # SNS Topics
        elif res_type in ("aws_sns_topic", "sns_topic"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                seed["sns_topics"].append({"name": _sanitize_name(_resolved(props.get("name"), res_name), 256)})

        # SQS Queues
        elif res_type in ("aws_sqs_queue", "sqs_queue"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                seed["sqs_queues"].append({"name": _sanitize_name(_resolved(props.get("name"), res_name), 80)})

        # Security Groups
        elif res_type in ("aws_security_group", "security_group"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                tags = props.get("tags") if isinstance(props.get("tags"), dict) else {}
                seed["security_groups"].append({
                    "name": _sanitize_name(_resolved(props.get("name"), res_name), 255),
                    "description": _resolved(props.get("description"), "Terraform seeded security group"),
                    "tags": tags,
                })

        else:
            # Recognised as a resource block but Siege has no seeding/tooling for
            # it (yet) -- report it instead of silently dropping it (PRD §8.3).
            for res_name in instances.keys():
                unmapped.append({"resource_type": str(res_type), "resource_name": str(res_name)})

    # Clean up empty sections
    seed = {k: v for k, v in seed.items() if v}
    return TerraformParseResult(seed, unmapped)


def _extract_heredocs(block: str) -> tuple[str, dict[str, str]]:
    """Replace `key = <<-EOF ... EOF` heredocs with an opaque placeholder token
    so the naive line-by-line property parser below doesn't shred them into
    bogus keys, then hand back the verbatim heredoc bodies keyed by token so
    callers needing exact content (e.g. JSON policy documents) can recover it."""
    docs: dict[str, str] = {}

    def repl(m: re.Match[str]) -> str:
        key, _tag, body = m.groups()
        token = f"__SIEGE_HEREDOC_{len(docs)}__"
        docs[token] = body.strip("\n")
        return f'{key} = "{token}"'

    return _HEREDOC_RE.sub(repl, block), docs


def _parse_simple_hcl(content: str) -> TerraformParseResult:
    """Fallback parser for basic HCL resource declarations."""
    resources: dict[str, dict[str, Any]] = {}
    pattern = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{([\s\S]*?)\n\}', re.MULTILINE)
    for match in pattern.finditer(content):
        res_type, res_name, block = match.groups()
        if res_type not in resources:
            resources[res_type] = {}
        props: dict[str, Any] = {}

        block, heredocs = _extract_heredocs(block)

        # Extract nested blocks like tags = { ... } first
        tags_match = re.search(r'tags\s*=\s*\{([\s\S]*?)\}', block)
        if tags_match:
            tag_dict = {}
            for tline in tags_match.group(1).splitlines():
                tline = tline.strip().strip(",")
                if "=" in tline:
                    tk, tv = tline.split("=", 1)
                    tag_dict[tk.strip().strip('"').strip("'")] = tv.strip().strip('"').strip("'")
            props["tags"] = tag_dict
            # remove tags block from block string so it doesn't get processed line-by-line
            block = block[:tags_match.start()] + block[tags_match.end():]

        for line in block.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "//", "/*")):
                continue
            if "=" in line:
                key, val = line.split("=", 1)
                k = key.strip()
                v = val.strip().strip('"').strip("'")
                props[k] = heredocs.get(v, v)
        resources[res_type][res_name] = props
    return _convert_tf_resource_dict(resources)
