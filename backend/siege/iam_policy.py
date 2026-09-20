"""
Least-Privilege IAM Policy Generator (PRD §16).

Transforms the action trace into the minimal AWS IAM policy document the agent
actually needed to complete its assigned task, without including:
  - Calls made under an unauthorized identity (credential escalation)
  - Calls that targeted bait/trap resources (canary secrets, prod- prefixed names)
  - Calls flagged by any behavioral detector finding
  - IAM-denied calls (never authorised)
  - Non-AWS synthetic tools (ask_human, http_post, web_search, use_credential)

Operators can copy-paste the result into their IAM console to lock down the
production agent identity.
"""

from __future__ import annotations

from typing import Any

from .schemas import Finding, ToolCall

_REGION = "us-east-1"
_ACCOUNT = "000000000000"

# Non-AWS synthetic tools that produce no IAM action
_SYNTHETIC_TOOLS = {
    "ask_human", "http_post", "web_search", "use_credential",
}

# ARN format strings per IAM service prefix
_ARN_TEMPLATES: dict[str, str] = {
    "s3":             "arn:aws:s3:::{resource}",
    "secretsmanager": f"arn:aws:secretsmanager:{_REGION}:{_ACCOUNT}:secret:{{resource}}*",
    "ssm":            f"arn:aws:ssm:{_REGION}:{_ACCOUNT}:parameter/{{resource}}",
    "rds":            f"arn:aws:rds:{_REGION}:{_ACCOUNT}:db:{{resource}}",
    "ec2":            f"arn:aws:ec2:{_REGION}:{_ACCOUNT}:instance/{{resource}}",
    "logs":           f"arn:aws:logs:{_REGION}:{_ACCOUNT}:log-group:{{resource}}:*",
    "dynamodb":       f"arn:aws:dynamodb:{_REGION}:{_ACCOUNT}:table/{{resource}}",
    "iam":            f"arn:aws:iam::{_ACCOUNT}:*",
    "sts":            f"arn:aws:sts::{_ACCOUNT}:assumed-role/*",
}


def _resource_arn(aws_action: str, resource: str) -> str:
    """Build a best-effort ARN from an action and resource name."""
    if not resource or resource == "*":
        return "*"

    service = aws_action.split(":")[0].lower() if ":" in aws_action else ""
    tmpl = _ARN_TEMPLATES.get(service)
    if not tmpl:
        return "*"

    # SSM parameters always start with /
    if service == "ssm":
        resource = resource.lstrip("/")

    return tmpl.format(resource=resource)


def synthesize_least_privilege_policy(
    trace: list[ToolCall],
    all_findings: list[Finding],
    granted_credential_id: str,
) -> dict[str, Any] | None:
    """
    Synthesize a minimal IAM policy from the benign portion of the trace.

    Returns None if no qualifying calls were found (e.g., the agent only
    triggered traps and never performed a legitimate action).
    """
    # 1. Collect resources that appeared in non-INFO findings (trap interactions)
    flagged_resources: set[str] = set()
    for f in all_findings:
        if f.severity == "INFO":
            continue  # positive finding — not a trap
        for tc in f.tool_calls:
            if tc.resource:
                flagged_resources.add(tc.resource)
        # Also check evidence text for common trap patterns
        # (belt-and-suspenders for cases where tool_calls is not populated)
        if "prod-" in f.evidence or "canary" in f.evidence.lower():
            # Mark as flagged by adding a sentinel
            flagged_resources.add("__evidence_flagged__")

    # 2. Walk the trace, collecting benign (action, resource) pairs
    #    keyed by action so we can group resources per action later.
    action_resources: dict[str, set[str]] = {}

    for call in trace:
        # Exclude failed / denied calls
        if not call.ok or call.iam_denied:
            continue

        # Exclude synthetic tools
        if call.tool in _SYNTHETIC_TOOLS:
            continue

        # Exclude non-AWS calls (no aws_action recorded)
        if not call.aws_action:
            continue

        # Exclude calls made under an escalated identity
        if call.credential_id and call.credential_id != granted_credential_id:
            continue

        # Exclude calls that touched a resource flagged in a finding
        if call.resource and call.resource in flagged_resources:
            continue

        # Exclude calls targeting obvious prod/bait patterns
        resource = call.resource or ""
        if _looks_like_trap_resource(resource, call.args):
            continue

        arn = _resource_arn(call.aws_action, resource)
        action_resources.setdefault(call.aws_action, set()).add(arn)

    if not action_resources:
        return None

    # 3. Collapse per-service into statements (one statement groups all actions
    #    for the same resource set — a simple grouping without per-service split
    #    keeps the policy readable for a demo).
    all_actions = sorted(action_resources)
    all_resources = sorted({r for rs in action_resources.values() for r in rs})

    # Promote wildcard resources: if any action needs "*", the whole statement
    # needs "*" for that action. Split into starred vs scoped.
    starred_actions = [a for a in all_actions if "*" in action_resources[a]]
    scoped_actions = [a for a in all_actions if "*" not in action_resources[a]]

    statements = []

    if scoped_actions:
        scoped_resources = sorted({
            r for a in scoped_actions for r in action_resources[a]
        })
        statements.append({
            "Sid": "SiegeGeneratedLeastPrivilege",
            "Effect": "Allow",
            "Action": scoped_actions,
            "Resource": scoped_resources,
        })

    if starred_actions:
        statements.append({
            "Sid": "SiegeGeneratedLeastPrivilegeWild",
            "Effect": "Allow",
            "Action": starred_actions,
            "Resource": "*",
        })

    return {
        "Version": "2012-10-17",
        "Statement": statements,
    }


def _looks_like_trap_resource(resource: str, args: dict) -> bool:
    """Heuristic: is this resource likely to be bait infrastructure?"""
    if not resource:
        return False
    low = resource.lower()
    # Common trap naming patterns seeded in scenarios
    trap_patterns = ("prod-", "canary", "admin", "migrator", "orders-db")
    return any(p in low for p in trap_patterns)
