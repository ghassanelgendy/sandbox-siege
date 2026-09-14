"""
Terraform / OpenTofu HCL / YAML infra parser and LocalStack sandbox seeder.

Allows users to import their actual infrastructure declarations (e.g. aws_s3_bucket,
aws_db_instance, aws_instance, aws_secretsmanager_secret, aws_dynamodb_table,
aws_cloudwatch_log_group) directly into Sandbox Siege scenarios so that testing
takes place against exact replicas of production infrastructure rather than toy mocks.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
import yaml

logger = logging.getLogger("siege.terraform")


def parse_terraform_structure(raw_content: str) -> dict[str, Any]:
    """Parse Terraform declared resources in YAML, JSON, or HCL-like format into Sandbox Siege seed dict."""
    content = raw_content.strip()
    if not content:
        return {}

    parsed: dict[str, Any] = {}

    # 1. Try direct YAML / JSON
    try:
        data = yaml.safe_load(content)
        if isinstance(data, dict):
            # Check if it's nested under resource or terraform block
            if "resource" in data:
                return _convert_tf_resource_dict(data["resource"])
            elif "terraform" in data and isinstance(data["terraform"], dict) and "resource" in data["terraform"]:
                return _convert_tf_resource_dict(data["terraform"]["resource"])
            elif any(k in data for k in ("buckets", "rds", "ec2", "secrets", "tables", "log_groups")):
                # Already a native seed dict
                return data
            else:
                return _convert_tf_resource_dict(data)
    except Exception:
        pass

    # 2. Try HCL block regex parsing (simple fallback for resource "aws_..." "name" { ... })
    return _parse_simple_hcl(content)


def _convert_tf_resource_dict(resources: dict[str, Any]) -> dict[str, Any]:
    """Convert parsed Terraform resource definitions to Sandbox Siege seed schema."""
    seed: dict[str, Any] = {
        "buckets": [],
        "objects": [],
        "secrets": [],
        "parameters": [],
        "tables": [],
        "rds": [],
        "ec2": [],
        "log_groups": [],
    }

    for res_type, instances in resources.items():
        if not isinstance(instances, dict):
            continue

        # S3 Buckets
        if res_type in ("aws_s3_bucket", "s3_bucket", "s3"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                bucket_name = props.get("bucket", res_name)
                seed["buckets"].append(bucket_name)

        # S3 Objects
        elif res_type in ("aws_s3_object", "aws_s3_bucket_object", "s3_object"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                seed["objects"].append({
                    "bucket": props.get("bucket", "default-bucket"),
                    "key": props.get("key", res_name),
                    "body": props.get("content", props.get("body", "terraform-seeded-content")),
                })

        # RDS Instances
        elif res_type in ("aws_db_instance", "db_instance", "rds"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                ident = props.get("identifier", props.get("db_instance_identifier", res_name))
                tags = props.get("tags") or {}
                seed["rds"].append({
                    "db_instance_identifier": ident,
                    "engine": props.get("engine", "postgres"),
                    "db_instance_class": props.get("instance_class", props.get("db_instance_class", "db.t3.micro")),
                    "allocated_storage": props.get("allocated_storage", 20),
                    "tags": tags,
                    "snapshots": props.get("snapshots", [f"{ident}-snap-latest"]),
                })

        # EC2 Instances
        elif res_type in ("aws_instance", "instance", "ec2"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                raw_tags = props.get("tags")
                tags = raw_tags if isinstance(raw_tags, dict) else {}
                seed["ec2"].append({
                    "name": tags.get("Name", res_name) if isinstance(tags, dict) else res_name,
                    "instance_type": props.get("instance_type", "t3.small"),
                    "count": int(props.get("count", 1)) if str(props.get("count", 1)).isdigit() else 1,
                    "tags": tags,
                })

        # Secrets Manager
        elif res_type in ("aws_secretsmanager_secret", "secretsmanager_secret", "secrets"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                seed["secrets"].append({
                    "name": props.get("name", res_name),
                    "description": props.get("description", "Terraform seeded secret"),
                    "value": props.get("secret_string", props.get("value", '{"status":"active"}')),
                })

        # DynamoDB Tables
        elif res_type in ("aws_dynamodb_table", "dynamodb_table", "tables"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                seed["tables"].append({
                    "name": props.get("name", res_name),
                    "hash_key": props.get("hash_key", "id"),
                })

        # CloudWatch Log Groups
        elif res_type in ("aws_cloudwatch_log_group", "cloudwatch_log_group", "log_groups"):
            for res_name, res_props in instances.items():
                props = res_props if isinstance(res_props, dict) else {}
                seed["log_groups"].append({
                    "name": props.get("name", f"/aws/{res_name}"),
                    "streams": props.get("streams", [{"name": "app-stream", "events": ["[INFO] Infrastructure provisioned via Terraform."]}]),
                })

    # Clean up empty sections
    return {k: v for k, v in seed.items() if v}


def _parse_simple_hcl(content: str) -> dict[str, Any]:
    """Fallback parser for basic HCL resource declarations."""
    resources: dict[str, dict[str, Any]] = {}
    pattern = re.compile(r'resource\s+"([^"]+)"\s+"([^"]+)"\s*\{([\s\S]*?)\n\}', re.MULTILINE)
    for match in pattern.finditer(content):
        res_type, res_name, block = match.groups()
        if res_type not in resources:
            resources[res_type] = {}
        props: dict[str, Any] = {}

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
                props[k] = v
        resources[res_type][res_name] = props
    return _convert_tf_resource_dict(resources)
