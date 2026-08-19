"""
Replay (PRD FR-8.1 .. FR-8.4) -- the demo safety net.

Re-emits a recorded events.jsonl through the same bus. Makes ZERO calls to model
providers or LocalStack, so it works with the network off and the UI cannot tell
the difference.
"""

from __future__ import annotations

import asyncio

from ..events import RunChannel, read_events
from ..orchestrator import load_report
from ..schemas import Report

MAX_GAP_S = 2.0  # never stall a live demo on a long original pause (FR-8.2)


async def replay_run(source_run_id: str, channel: RunChannel, speed: float = 1.0) -> Report | None:
    """Stream a recorded run into `channel`, preserving relative pacing."""
    events = read_events(source_run_id)
    speed = max(0.1, float(speed or 1.0))

    previous_ts = None
    for event in events:
        if previous_ts is not None:
            gap = (event.ts - previous_ts).total_seconds() / speed
            if gap > 0:
                await asyncio.sleep(min(gap, MAX_GAP_S))
        previous_ts = event.ts
        replayed = event.model_copy(update={"run_id": channel.run_id})
        channel.publish(replayed)

    channel.close()

    report = load_report(source_run_id)
    if report is not None:
        report = report.model_copy(update={"run_id": channel.run_id, "mode": "replay"})
        from ..orchestrator import _persist
        _persist(report)
    return report
