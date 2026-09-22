"""On-demand Resend report email (D-52).

Ports the HTML template already proven in `.github/workflows/siege-gate.yml`'s
CI dispatch (D-32) into Python so the `/demo` spectator page (backend/siege/demo.html)
can send a judge their own copy the moment a run finishes. Same palette, same
layout — deliberately not a redesign.
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request

from .config import settings
from .schemas import Report

RESEND_URL = "https://api.resend.com/emails"


class EmailSendError(RuntimeError):
    """Raised when Resend rejects the send or no API key is configured."""


def _badge(outcome: str) -> str:
    outcome = outcome.lower()
    if outcome == "pass":
        return ('<span style="background:#1F4738;color:#6FD3A6;padding:3px 8px;border-radius:4px;'
                'font-size:11px;font-weight:700;letter-spacing:0.05em">PASS</span>')
    if outcome == "partial":
        return ('<span style="background:#6B4E28;color:#E0A458;padding:3px 8px;border-radius:4px;'
                'font-size:11px;font-weight:700;letter-spacing:0.05em">WARN</span>')
    return ('<span style="background:#5E1F22;color:#E5484D;padding:3px 8px;border-radius:4px;'
            'font-size:11px;font-weight:700;letter-spacing:0.05em">FAIL</span>')


def render_report_email(report: Report) -> tuple[str, str]:
    """Returns (subject, html) for a finished Report."""
    is_pass = report.gate == "PASS"
    accent = "#6FD3A6" if is_pass else "#E5484D"
    gate_bg = "#1F4738" if is_pass else "#5E1F22"
    gate_label = "GATE PASSED" if is_pass else "GATE FAILED"
    subject = f"{'🟢' if is_pass else '🔴'} [{gate_label}] Sandbox Siege · {report.model} · Trust {report.trust_score:g}"

    rows = ""
    for s in report.scenarios:
        non_info = [f for f in s.findings if f.severity != "INFO"]
        traps = " ".join(
            f'<span style="background:#18232F;color:#E5484D;border:1px solid #5E1F22;padding:2px 6px;'
            f'border-radius:3px;font-size:11px;font-family:monospace;margin-right:4px">{f.trap_id}</span>'
            for f in non_info
        ) or '<span style="color:#61738A;font-size:12px">—</span>'
        rows += f"""
        <tr style="border-bottom:1px solid #1E2A36">
          <td style="padding:10px 8px;font-family:monospace;font-size:12px;color:#E0A458;font-weight:600">{s.id}</td>
          <td style="padding:10px 8px;font-size:13px;color:#E4EAF0">{s.title}</td>
          <td style="padding:10px 8px">{_badge(s.outcome)}</td>
          <td style="padding:10px 8px;font-family:monospace;font-size:13px;color:#96A6B8">{s.score:g}<span style="color:#61738A">/{s.max_score:g}</span></td>
          <td style="padding:10px 8px">{traps}</td>
        </tr>"""

    eff = report.efficiency
    efficiency_stats = (f"{eff.tool_calls} tool calls · {eff.tokens_in + eff.tokens_out:,} tokens · "
                        f"~{eff.est_gco2e:g} gCO₂e")

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background-color:#070A0E;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#E4EAF0">
<table width="100%" cellpadding="0" cellspacing="0" style="background-color:#070A0E;padding:32px 12px">
<tr><td align="center">
<table width="680" cellpadding="0" cellspacing="0" style="max-width:680px;background:#0B1016;border:1px solid #1E2A36;border-radius:12px;overflow:hidden;box-shadow:0 12px 36px rgba(0,0,0,0.5)">
  <tr>
    <td style="background:linear-gradient(90deg, #121A23 0%, #18232F 100%);padding:24px 28px;border-bottom:1px solid #1E2A36">
      <table width="100%" cellpadding="0" cellspacing="0"><tr>
        <td>
          <div style="font-family:'Courier New',Courier,monospace;font-size:11px;font-weight:700;letter-spacing:0.18em;color:#E0A458;text-transform:uppercase;margin-bottom:4px">CHAOS ENGINEERING FOR AI AGENTS</div>
          <div style="font-size:22px;font-weight:800;color:#FFFFFF;letter-spacing:-0.02em">SANDBOX<span style="color:#E0A458">SIEGE</span></div>
        </td>
        <td align="right" valign="middle">
          <span style="display:inline-block;padding:6px 14px;border-radius:6px;background:{gate_bg};color:{accent};font-size:12px;font-weight:800;letter-spacing:0.08em;font-family:monospace;border:1px solid {accent}40">{gate_label}</span>
        </td>
      </tr></table>
    </td>
  </tr>
  <tr><td style="padding:24px 28px 12px">
    <table width="100%" cellpadding="0" cellspacing="0"><tr>
      <td width="31%" style="background:#121A23;border:1px solid #1E2A36;border-radius:8px;padding:16px;text-align:center">
        <div style="font-size:10px;font-weight:700;color:#96A6B8;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:6px">TRUST SCORE</div>
        <div style="font-size:32px;font-weight:800;color:{accent};font-family:monospace;line-height:1">{report.trust_score:g}<span style="font-size:14px;color:#61738A">/100</span></div>
        <div style="font-size:11px;color:#96A6B8;margin-top:6px">Grade <strong style="color:#FFFFFF">{report.grade}</strong> (Req: {report.threshold:g})</div>
      </td>
      <td width="3.5%"></td>
      <td width="31%" style="background:#121A23;border:1px solid #1E2A36;border-radius:8px;padding:16px;text-align:center">
        <div style="font-size:10px;font-weight:700;color:#96A6B8;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:6px">PASS RATE</div>
        <div style="font-size:26px;font-weight:800;color:#FFFFFF;font-family:monospace;line-height:1.2"><span style="color:#6FD3A6">{report.totals.passed}</span> / <span style="color:#E5484D">{report.totals.failed}</span></div>
        <div style="font-size:11px;color:#96A6B8;margin-top:6px">{report.totals.passed} pass · {report.totals.partial} warn · {report.totals.failed} fail</div>
      </td>
      <td width="3.5%"></td>
      <td width="31%" style="background:#121A23;border:1px solid #1E2A36;border-radius:8px;padding:16px;text-align:center">
        <div style="font-size:10px;font-weight:700;color:#96A6B8;letter-spacing:0.1em;text-transform:uppercase;margin-bottom:6px">TARGET MODEL</div>
        <div style="font-size:13px;font-weight:700;color:#E0A458;font-family:monospace;line-height:1.3;word-break:break-all">{report.model}</div>
        <div style="font-size:11px;color:#96A6B8;margin-top:6px">LocalStack Pro sandbox</div>
      </td>
    </tr></table>
  </td></tr>
  <tr><td style="padding:8px 28px 24px">
    <table width="100%" cellpadding="0" cellspacing="0">
      <tr><td style="font-size:10px;font-weight:700;color:#96A6B8;letter-spacing:0.1em;text-transform:uppercase;padding-bottom:8px">SCENARIO BREAKDOWN</td></tr>
      <tr><td>
        <table width="100%" cellpadding="0" cellspacing="0" style="border-collapse:collapse">{rows}</table>
      </td></tr>
      <tr><td style="padding-top:14px;font-size:12px;color:#96A6B8">{efficiency_stats}</td></tr>
    </table>
  </td></tr>
  <tr><td style="padding:18px 28px;border-top:1px solid #1E2A36;font-size:11px;color:#61738A">
    Sent from a live Sandbox Siege demo run — run id <span style="font-family:monospace;color:#96A6B8">{report.run_id}</span>.
  </td></tr>
</table>
</td></tr></table>
</body>
</html>"""
    return subject, html


def send_report_email(report: Report, to_addr: str) -> None:
    """Sends `report` to `to_addr` via Resend. Raises EmailSendError on any failure."""
    if not settings.resend_api_key:
        raise EmailSendError("RESEND_API_KEY is not configured on the server")

    subject, html = render_report_email(report)
    payload = json.dumps({
        "from": settings.report_email_from,
        "to": [to_addr],
        "subject": subject,
        "html": html,
    }).encode()

    req = urllib.request.Request(
        RESEND_URL,
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.resend_api_key}",
            "Content-Type": "application/json",
            "User-Agent": "sandbox-siege-demo/1.0",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status >= 300:
                raise EmailSendError(f"Resend returned HTTP {resp.status}")
    except urllib.error.HTTPError as exc:
        raise EmailSendError(f"Resend error {exc.code}: {exc.read().decode(errors='replace')}") from exc
    except urllib.error.URLError as exc:
        raise EmailSendError(f"Could not reach Resend: {exc.reason}") from exc
