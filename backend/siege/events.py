"""
In-process event bus (PRD FR-6.1 .. FR-6.4).

Every event is simultaneously:
  1. appended to runs/<run_id>/events.jsonl  -- the replay tape
  2. fanned out to any open SSE subscribers
A subscriber attaching mid-run receives the buffered backlog first, then live
events, so there are never gaps.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

from .config import RUNS_DIR
from .schemas import Event


class RunChannel:
    """Buffer + live fan-out for a single run."""

    def __init__(self, run_id: str, persist: bool = True) -> None:
        self.run_id = run_id
        self.persist = persist
        self.buffer: list[Event] = []
        self.subscribers: set[asyncio.Queue[Event | None]] = set()
        self.closed = False
        self.stopped = False
        self._seq = 0
        self._path: Path | None = None
        if persist:
            d = RUNS_DIR / run_id
            d.mkdir(parents=True, exist_ok=True)
            self._path = d / "events.jsonl"
            self._path.write_text("", encoding="utf-8")

    def stop(self) -> None:
        self.stopped = True
        self.emit("run.error", {"message": "Run stopped by user"})

    def next_seq(self) -> int:
        self._seq += 1
        return self._seq

    def emit(self, type_: str, data: dict[str, Any], scenario_id: str | None = None) -> Event:
        event = Event(
            seq=self.next_seq(),
            run_id=self.run_id,
            scenario_id=scenario_id,
            type=type_,
            data=data,
        )
        self.publish(event)
        return event

    def publish(self, event: Event) -> None:
        """Publish a pre-built event (used by replay, which reuses recorded seq/ts)."""
        self.buffer.append(event)
        if self._path is not None:
            with self._path.open("a", encoding="utf-8") as fh:
                fh.write(event.model_dump_json() + "\n")
        for q in list(self.subscribers):
            q.put_nowait(event)

    def subscribe(self) -> asyncio.Queue[Event | None]:
        q: asyncio.Queue[Event | None] = asyncio.Queue()
        for event in self.buffer:  # backlog first — no gaps (FR-6.4)
            q.put_nowait(event)
        if self.closed:
            q.put_nowait(None)
        else:
            self.subscribers.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[Event | None]) -> None:
        self.subscribers.discard(q)

    def close(self) -> None:
        self.closed = True
        for q in list(self.subscribers):
            q.put_nowait(None)
        self.subscribers.clear()
        bus.drop(self.run_id)


class EventBus:
    def __init__(self) -> None:
        self._channels: dict[str, RunChannel] = {}

    def create(self, run_id: str, persist: bool = True) -> RunChannel:
        ch = RunChannel(run_id, persist=persist)
        self._channels[run_id] = ch
        return ch

    def get(self, run_id: str) -> RunChannel | None:
        return self._channels.get(run_id)

    def drop(self, run_id: str) -> None:
        self._channels.pop(run_id, None)


bus = EventBus()


def read_events(run_id: str) -> list[Event]:
    """Load a recorded event tape from disk (used by replay)."""
    path = RUNS_DIR / run_id / "events.jsonl"
    if not path.exists():
        raise FileNotFoundError(f"No recorded events for run {run_id!r} at {path}")
    out: list[Event] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            out.append(Event.model_validate(json.loads(line)))
    return out
