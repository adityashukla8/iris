"""
Shared in-process state: alert event bus, shift counters, healing queue.
Single source of truth for dashboard + orchestrator + healing pipeline.
"""
from __future__ import annotations

import asyncio
from collections import deque
from datetime import datetime, timezone

from sdk.models import AlertEvent, SelfHealEvent

alert_bus: asyncio.Queue[AlertEvent] = asyncio.Queue(maxsize=500)
self_heal_bus: asyncio.Queue[SelfHealEvent] = asyncio.Queue(maxsize=100)

recent_traces: deque[dict] = deque(maxlen=200)

# ── Activity log (ADK orchestration + MCP interaction events) ─────────────────
activity_log: deque[dict] = deque(maxlen=500)
_activity_subscribers: list[asyncio.Queue] = []


def push_activity(text: str, level: str = "info") -> None:
    """Broadcast an activity event to the live log and all SSE subscribers."""
    event = {
        "ts": datetime.now(timezone.utc).strftime("%H:%M:%S"),
        "text": text,
        "level": level,
    }
    activity_log.appendleft(event)
    for q in list(_activity_subscribers):
        try:
            q.put_nowait(event)
        except Exception:
            pass

shift_stats: dict[str, int | float] = {
    "total_traces": 0,
    "hallucinations_caught": 0,
    "self_heals": 0,
    "human_escalations": 0,
}

# Self-healing pipeline state
# Imported lazily to avoid circular import at module load time
# (core.healing.models imports core.config which imports nothing from core.state)
from core.healing.models import HealingCandidate  # noqa: E402

healing_candidates: deque[HealingCandidate] = deque(maxlen=50)   # pending human review
healing_history: deque[HealingCandidate] = deque(maxlen=200)     # all past candidates
