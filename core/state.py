"""
Shared in-process state: alert event bus, shift counters, healing queue.
Single source of truth for dashboard + orchestrator + healing pipeline.
"""
from __future__ import annotations

import asyncio
import time
from collections import deque
from datetime import datetime, timezone

from sdk.models import AlertEvent, SelfHealEvent

alert_bus: asyncio.Queue[AlertEvent] = asyncio.Queue(maxsize=500)
self_heal_bus: asyncio.Queue[SelfHealEvent] = asyncio.Queue(maxsize=100)

recent_traces: deque[dict] = deque(maxlen=200)

# ── Activity log (ADK event stream + healing pipeline events) ─────────────────
activity_log: deque[dict] = deque(maxlen=500)
_activity_subscribers: list[asyncio.Queue] = []


def push_activity(text: str, level: str = "info") -> None:
    """Broadcast an activity event to the live log and all SSE subscribers."""
    event = {
        "ts": datetime.now(timezone.utc).isoformat(),
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

# ── Autonomous scan guards ─────────────────────────────────────────────────────
# Only one scan may run at a time. Any trigger that finds the lock held is
# silently skipped (logged to activity feed).
scan_lock: asyncio.Lock = asyncio.Lock()

# Monotonic timestamp of the most recent scan start. Used for scheduler debounce
# (skip the 30-min slot if a manual or event-driven scan just ran).
last_scan_time: float = 0.0

# Per-cluster cooldown after a heal attempt. Keyed by f"{agent}|{prompt_hash}|{query_type}".
# Value = monotonic time of the most recent heal attempt for that cluster.
heal_cooldowns: dict[str, float] = {}


def record_heal_cooldown(agent: str, prompt_hash: str, query_type: str) -> None:
    key = f"{agent}|{prompt_hash}|{query_type}"
    heal_cooldowns[key] = time.monotonic()


def is_cluster_in_cooldown(agent: str, prompt_hash: str, query_type: str, cooldown_seconds: float) -> bool:
    key = f"{agent}|{prompt_hash}|{query_type}"
    last = heal_cooldowns.get(key)
    return last is not None and (time.monotonic() - last) < cooldown_seconds


# ── Self-healing pipeline state ────────────────────────────────────────────────
# Imported lazily to avoid circular import at module load time
# (core.healing.models imports core.config which imports nothing from core.state)
from core.healing.models import HealingCandidate  # noqa: E402

healing_candidates: deque[HealingCandidate] = deque(maxlen=50)   # pending human review
healing_history: deque[HealingCandidate] = deque(maxlen=200)     # all past candidates
