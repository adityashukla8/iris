"""
Shared in-process state: alert event bus, shift counters, healing queue.
Single source of truth for dashboard + orchestrator + healing pipeline.
"""
from __future__ import annotations

import asyncio
from collections import deque

from sdk.models import AlertEvent, SelfHealEvent

alert_bus: asyncio.Queue[AlertEvent] = asyncio.Queue(maxsize=500)
self_heal_bus: asyncio.Queue[SelfHealEvent] = asyncio.Queue(maxsize=100)

recent_traces: deque[dict] = deque(maxlen=200)

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
