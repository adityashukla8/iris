"""
Phoenix MCP response filter — strips bloated span attributes before they enter
the LLM context.

Phoenix stores gcp.vertex.agent.llm_request/llm_response on every ADK-generated
span. Each attribute is the full Gemini request/response (system prompt + tool
definitions + conversation) serialised as JSON. For 10 spans this alone is
200K+ chars (~50K tokens), which hits Gemini's 1M-token ceiling.

Registered as after_tool_callback on pattern_detector and self_healer so that
get-spans, get-span-annotations, and list-traces responses are stripped before
the LLM sees them. Return None = pass through; return dict = replacement.
"""
from __future__ import annotations

import json
from typing import Any, Optional

# Strip by exact attribute name
_STRIP_ATTRS: frozenset[str] = frozenset({
    "gcp.vertex.agent.llm_request",
    "gcp.vertex.agent.llm_response",
    "gcp.vertex.agent.llm_response_usage",
    "gcp.vertex.agent.invocation_id",
    "openinference.span.kind",
    "input.value",               # full Gemini request JSON — massive
    "output.value",              # full Gemini response JSON — massive
    "input.mime_type",
    "output.mime_type",
    "llm.invocation_parameters", # system prompt repeated in full
    "llm.finish_reason",
    "llm.system",
    "llm.provider",
})

# Strip all attributes whose key starts with any of these prefixes
_STRIP_ATTR_PREFIXES: tuple[str, ...] = (
    "llm.tools.",              # full tool JSON schemas per tool
    "llm.input_messages.",     # full conversation history
    "llm.output_messages.",    # full LLM output messages
    "gen_ai.response.",        # finish reasons, etc.
    "gen_ai.usage.",           # token counts (keep llm.token_count.* instead)
    "gen_ai.operation.",
    "gen_ai.request.",
    "gen_ai.system",
    "gcp.vertex.agent.event_id",
    "gcp.vertex.agent.tool_response",
    "gcp.vertex.agent.tool_call_args",
    "tool.parameters.",        # full tool call arguments
    "tool.description",
    "gen_ai.tool.description",
    "gen_ai.tool.call.id",
)

# Top-level span fields the agents actually use
_KEEP_SPAN_FIELDS: frozenset[str] = frozenset({
    "id", "name", "context", "span_kind", "parent_id",
    "start_time", "end_time", "status_code", "status_message", "attributes",
})

# Annotation fields needed for failure scoring
_KEEP_ANNOTATION_FIELDS: frozenset[str] = frozenset({
    "id", "span_id", "name", "result", "annotator_kind",
})

_MAX_ATTR_VALUE_LEN = 300  # chars — truncate remaining long values


def _filter_span(span: dict) -> dict:
    out = {k: v for k, v in span.items() if k in _KEEP_SPAN_FIELDS}
    if "attributes" in out:
        cleaned: dict = {}
        for k, v in out["attributes"].items():
            if k in _STRIP_ATTRS:
                continue
            if any(k.startswith(p) for p in _STRIP_ATTR_PREFIXES):
                continue
            if isinstance(v, str) and len(v) > _MAX_ATTR_VALUE_LEN:
                v = v[:_MAX_ATTR_VALUE_LEN] + "…"
            cleaned[k] = v
        out["attributes"] = cleaned
    return out


def _filter_annotation(ann: dict) -> dict:
    return {k: v for k, v in ann.items() if k in _KEEP_ANNOTATION_FIELDS}


def phoenix_mcp_before_tool_callback(
    tool: Any,
    args: dict[str, Any],
    tool_context: Any,
) -> Optional[dict[str, Any]]:
    """
    ADK before_tool_callback: clamp arguments the LLM sometimes inflates past
    the Phoenix MCP schema bounds. get-spans rejects limit > 1000 with
    'MCP error -32602 ... too_big', which wastes a whole tool round-trip.
    Mutates args in place; returning None proceeds with the clamped call.
    """
    try:
        limit = args.get("limit")
        if isinstance(limit, (int, float)) and limit > 100:
            print(f"[MCP FILTER] clamping {getattr(tool, 'name', '?')} limit {limit} → 100")
            args["limit"] = 100
    except Exception:
        pass
    return None


def phoenix_mcp_after_tool_callback(
    tool: Any,
    args: dict[str, Any],
    tool_context: Any,
    tool_response: dict[str, Any],
) -> Optional[dict[str, Any]]:
    """
    ADK after_tool_callback: strip Phoenix MCP responses before the LLM sees them.
    Returns a rewritten response dict, or None to leave the original unchanged.
    """
    tool_name: str = getattr(tool, "name", "") or ""
    if tool_name not in ("get-spans", "get-span-annotations", "list-traces"):
        return None

    # MCP wraps all responses as: {"content": [{"type": "text", "text": "<json>"}]}
    raw_text = ""
    try:
        content = tool_response.get("content", [])
        if not content or content[0].get("type") != "text":
            return None

        raw_text = content[0].get("text") or ""
        if not raw_text.strip():
            print(f"[MCP FILTER] {tool_name}: empty response text — passing through")
            return None
        data = json.loads(raw_text)

        if tool_name == "get-spans" and "spans" in data:
            data["spans"] = [_filter_span(s) for s in data["spans"]]
            filtered = json.dumps(data)
            print(
                f"[MCP FILTER] get-spans: {len(data['spans'])} spans  "
                f"{len(raw_text):,} → {len(filtered):,} chars "
                f"({100 * (1 - len(filtered) / len(raw_text)):.0f}% reduction)"
            )
            return {"content": [{"type": "text", "text": filtered}]}

        if tool_name == "get-span-annotations" and "annotations" in data:
            data["annotations"] = [_filter_annotation(a) for a in data["annotations"]]
            filtered = json.dumps(data)
            print(
                f"[MCP FILTER] get-span-annotations: {len(data['annotations'])} annotations  "
                f"{len(raw_text):,} → {len(filtered):,} chars"
            )
            return {"content": [{"type": "text", "text": filtered}]}

        if tool_name == "list-traces":
            if "traces" in data:
                for trace in data["traces"]:
                    if "spans" in trace:
                        trace["spans"] = [_filter_span(s) for s in trace["spans"]]
            filtered = json.dumps(data)
            print(
                f"[MCP FILTER] list-traces  "
                f"{len(raw_text):,} → {len(filtered):,} chars"
            )
            return {"content": [{"type": "text", "text": filtered}]}

    except Exception as exc:
        # Non-JSON text is usually the MCP server relaying an upstream error
        # (Arize cloud hiccup). Pass it through untouched — the pattern
        # detector's deterministic fallback covers a failed read — but log
        # what Phoenix actually said so this is diagnosable.
        print(f"[MCP FILTER] parse error for {tool_name}: {exc} — payload head: {raw_text[:200]!r}")

    return None
