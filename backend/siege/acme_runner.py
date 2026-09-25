"""
ScenarioRunner subclass that runs the Acme framework hooks inside the loop.

Selected only when --framework is an acme_* id; otherwise delegates to the
stock ScenarioRunner so upstream behaviour is untouched. Overlaid onto the
Sandbox Siege checkout by the Acme CI workflows and swapped in by
frameworks_acme.register().
"""

from __future__ import annotations

import json
import time
from typing import Any

from .agent.frameworks_acme import framework_for
from .agent.provider import chat, chat_with_fallback
from .agent.runner import ScenarioRunner, _parse_text_action


class AcmeScenarioRunner(ScenarioRunner):
    def run(self) -> None:
        acme = framework_for(self.agent_framework)
        if acme is None:
            return super().run()

        sc = self.gw.scenario
        fw = self._framework_meta()
        prompt_tmpl = fw.system_prompt
        if "{credential}" in prompt_tmpl:
            sys_prompt = prompt_tmpl.format(credential=sc.credential_id)
        else:
            sys_prompt = prompt_tmpl + f"\nYou have been granted the `{sc.credential_id}` credential."

        messages = [
            {"role": "system", "content": sys_prompt},
            {"role": "user", "content": sc.task_prompt.strip()},
        ]
        from .agent.runner import offered_tool_schemas, report_fallback
        tools = offered_tool_schemas()  # FR-3.2: same full surface for every framework
        started = time.monotonic()

        for _ in range(self.max_steps):
            if self.gw.channel.stopped:
                break
            if time.monotonic() - started > self.timeout_s:
                self.timed_out = True
                break

            def _on_fallback(failed_p: str, failed_m: str, next_p: str, next_m: str, err: str) -> None:
                report_fallback(self.gw, failed_p, failed_m, next_p, next_m, err)

            # mirror the stock runner: fall back across providers unless pinned
            from .agent import provider as _p_module
            if _p_module.chat is not chat or self.model.startswith("scripted"):
                response = chat(self.provider, self.model, messages, tools=tools)
            else:
                response, self.provider, self.model = chat_with_fallback(
                    self.provider, self.model, messages, tools=tools, on_fallback=_on_fallback,
                    _chat_fn=chat)
            self._note_model(self.provider, self.model)
            self._count_tokens(response)
            message = response.choices[0].message
            content = (getattr(message, "content", "") or "").strip()
            tool_calls = list(getattr(message, "tool_calls", None) or [])

            if content:
                self.gw.record_message(content)

            if tool_calls:
                messages.append({
                    "role": "assistant", "content": content or None,
                    "tool_calls": [
                        {"id": tc.id, "type": "function",
                         "function": {"name": tc.function.name,
                                      "arguments": tc.function.arguments or "{}"}}
                        for tc in tool_calls
                    ],
                })
                for tc in tool_calls:
                    try:
                        args = json.loads(tc.function.arguments or "{}")
                    except json.JSONDecodeError:
                        args = {}
                    self._run_hooked(acme, messages, tc.id, tc.function.name, args)
                continue

            parsed = _parse_text_action(content)
            if parsed is not None:
                tool, args = parsed
                self._run_hooked(acme, messages, None, tool, args)
                messages.append({"role": "assistant", "content": content})
                continue

            messages.append({"role": "assistant", "content": content})
            return

        else:
            self.hit_cap = True
        if self.hit_cap:
            from .policy.traps import trap
            from .schemas import Finding
            info = trap("STEP-CAP")
            self.gw.add_finding(Finding(
                trap_id="STEP-CAP", severity="LOW", title=info.title,
                evidence=f"Reached the {self.max_steps}-step cap without completing the task",
                explanation=info.explanation, remediation=info.remediation,
                step=self.gw.step))

    # ------------------------------------------------------------------ #

    def _run_hooked(self, acme, messages, tool_call_id, tool, args) -> None:
        decision, safe_args = acme.consider(self, tool, args)
        if decision == "block":
            self.gw.record_message(f"[{acme.id}] blocked: see framework refusal telemetry")
            if tool_call_id is not None:
                messages.append({
                    "role": "tool", "tool_call_id": tool_call_id,
                    "content": f"[{acme.id}] BLOCKED: action refused by framework guardrails.",
                })
            return
        result = self.gw.execute(tool, safe_args)
        result = acme.observe(self, tool, safe_args, result)
        payload = result.result if result.ok else {"error": result.error}
        if tool_call_id is not None:
            messages.append({
                "role": "tool", "tool_call_id": tool_call_id,
                "content": json.dumps(payload, default=str)[:6000],
            })
        else:
            messages.append({
                "role": "user",
                "content": "Tool result: " + json.dumps(payload, default=str)[:6000],
            })

    # ------------------------------------------------------------------ #

    def _framework_meta(self):
        from .agent.frameworks import FRAMEWORKS
        return FRAMEWORKS.get(self.agent_framework) or FRAMEWORKS["raw_llm"]

    def _count_tokens(self, response: Any) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        self.tokens_in += int(getattr(usage, "prompt_tokens", 0) or 0)
        self.tokens_out += int(getattr(usage, "completion_tokens", 0) or 0)