"""
Prompt identity at scale.

IRIS may monitor thousands of interactions across many agents, each running its own
system prompt. To know WHICH prompt produced a failure (and therefore which one to heal),
we give every system prompt a deterministic content-hash identity and namespace prompt
versions per agent in Phoenix. This replaces the former single hardcoded
`settings.healing_prompt_name = "orion-clinical-safety"`.

  prompt_hash(system_prompt)      → stable 12-char id of the exact prompt text
  agent_prompt_name(agent_name)   → Phoenix prompt name namespaced to the agent

Hash-based prompt versioning is the industry-standard identity (Langfuse, PromptLayer,
MLflow): the same text always maps to the same id, so failures cluster cleanly by
(agent, prompt_hash) and a healed prompt becomes a new version under the agent's namespace.
"""
from __future__ import annotations

import hashlib
import re

_EMPTY_HASH = "none"


def prompt_hash(system_prompt: str | None) -> str:
    """Deterministic 12-char identity for a system prompt's exact text.

    Returns "none" when no system prompt was supplied, so events that predate
    system-prompt ingestion still group together rather than each looking unique.
    """
    text = (system_prompt or "").strip()
    if not text:
        return _EMPTY_HASH
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _slug(agent_name: str | None) -> str:
    raw = (agent_name or "agent").strip().lower()
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-")
    return slug or "agent"


def agent_prompt_name(agent_name: str | None) -> str:
    """Phoenix prompt name for an agent's system prompt, namespaced per agent.

    e.g. "ORION" -> "orion-system". Each heal adds a new version under this name,
    tagged with the new content hash (+ 'production' once approved).
    """
    return f"{_slug(agent_name)}-system"
