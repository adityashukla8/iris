"""
Live demo agent — generates clinical answers at run time with Gemini under the
agent's *current* prompt: the production-tagged healed version from Phoenix if
a heal has deployed, otherwise the simulator's weak baseline prompt.

This closes the self-healing loop for the demo. Recorded mode replays captured
unsafe outputs (guaranteed failures); after IRIS heals the prompt, re-running
the same scenarios in live mode produces genuinely different answers, which the
evaluators score fresh — so the before/after improvement is real, not staged.

Unlike the validation responder in core/healing/experiment.py, the template
here adds NO safety scaffold: prompt quality alone must drive the outcome.
"""
from __future__ import annotations

import json

from core.config import settings
from core.healing.diagnose import _extract_template_text
from core.healing.prompt_identity import agent_prompt_name, prompt_hash
from core.healing.prompt_manager import prompt_manager
from core.llm import generate_text


async def get_effective_prompt(agent_name: str) -> tuple[str, str, str]:
    """Resolve the prompt the live agent runs under.

    Returns (prompt_text, source, phash) where source is 'production' (healed
    version tagged in Phoenix) or 'baseline' (the simulator's weak prompt).
    """
    pname = agent_prompt_name(agent_name)
    data = await prompt_manager.get_prompt_by_tag(pname, "production")
    if data:
        text = _extract_template_text(data)
        if text:
            return text, "production", prompt_hash(text)
    from demo.mock_agents.simulator import AGENT_SYSTEM_PROMPT
    return AGENT_SYSTEM_PROMPT, "baseline", prompt_hash(AGENT_SYSTEM_PROMPT)


_LIVE_PROMPT = """\
{system_prompt}

Patient context: {context}
Clinical question: {question}

Your answer:"""


async def generate_live_output(
    system_prompt: str, input_prompt: str, retrieved_context: dict
) -> str:
    """Generate the agent's answer under the given prompt."""
    # Deterministic: same prompt + scenario → same answer on every run,
    # so comparison numbers are stable across demo takes.
    text = await generate_text(
        _LIVE_PROMPT.format(
            system_prompt=system_prompt[:1500],
            context=json.dumps(retrieved_context, default=str)[:1500],
            question=input_prompt[:600],
        ),
        model=settings.gemini_model,
        temperature=0.0,
        seed=42,
        tag="LiveAgent",
    )
    text = (text or "").strip()
    if not text:
        raise ValueError("live agent returned empty output")
    return text
