"""
Base Guard Interface for Agent Frameworks.
"""

from __future__ import annotations

from typing import Any

from ..schemas import ToolResult


class BaseGuard:
    """Base interface for framework behavioral and policy guards."""

    def __init__(self, framework_id: str) -> None:
        self.framework_id = framework_id

    def consider(self, runner: Any, tool: str, args: dict[str, Any]) -> tuple[str, dict[str, Any]]:
        """Return ("allow" | "block" | "modify", args). Called before execution."""
        return "allow", args

    def observe(self, runner: Any, tool: str, args: dict[str, Any], result: ToolResult) -> ToolResult:
        """Called with the executed result. May mutate or redact it."""
        return result

    def _refuse(self, runner: Any, tool: str, args: dict[str, Any], reason: str) -> None:
        msg = f"[{self.framework_id}] refused {tool}({args}) — {reason}"
        runner.gw.record_message(msg)
        runner.gw.channel.emit("framework.refusal", {
            "tool": tool,
            "args": args,
            "reason": reason,
            "framework": self.framework_id,
        })
