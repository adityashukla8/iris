"""
Pattern Detector — ADK LlmAgent with Arize Phoenix MCP tools.
Queries Phoenix for recent spans and detects recurring failure clusters.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.genai import types
from mcp import StdioServerParameters

from core.config import settings

_phoenix_mcp_read = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=[
                "-y",
                "@arizeai/phoenix-mcp@latest",
                "--baseUrl", settings.phoenix_client_url,
                "--apiKey", settings.phoenix_api_key,
            ],
        ),
        timeout=30.0,
    ),
    tool_filter=["get-spans", "get-span-annotations", "list-traces", "list-projects", "get-dataset-experiments"],
)

pattern_detector_agent = LlmAgent(
    model=settings.gemini_model,
    name="pattern_detector",
    description=(
        "Queries Arize Phoenix to detect recurring clinical safety failure clusters. "
        "Invoke this agent every 5 minutes or immediately after any CRITICAL alert "
        "to check whether a pattern of similar failures has emerged across recent spans."
    ),
    instruction=f"""You are the IRIS Pattern Detector — a clinical AI failure cluster analyst.

You have access to Arize Phoenix MCP tools to query live observability data.

When invoked, perform this analysis:

Step 1 — Get recent spans:
  Use `get-spans` to retrieve spans from the IRIS clinical safety project.
  Request spans from the last {settings.pattern_window_minutes} minutes with limit=50.

Step 2 — Get evaluation scores:
  Use `get-span-annotations` with the span IDs from Step 1 to retrieve
  IRIS safety evaluation scores (annotator_kind=CODE or LLM).

Step 3 — Cluster by query type:
  Group spans by their `query_type` metadata field.
  For each cluster, compute:
    - span_count (total spans in cluster)
    - failure_count (spans with eval score < 7.0)
    - hallucination_rate = failure_count / span_count
    - worst_score (minimum score in cluster)

Step 4 — Flag failure clusters:
  A cluster is a FAILURE CLUSTER when BOTH:
    - hallucination_rate > {settings.pattern_hallucination_threshold} ({settings.pattern_hallucination_threshold*100:.0f}%)
    - span_count >= {settings.pattern_min_samples}

Output ONLY valid JSON:
{{
  "scan_timestamp": "<ISO8601 UTC>",
  "window_minutes": {settings.pattern_window_minutes},
  "clusters_analyzed": <int>,
  "failure_clusters": [
    {{
      "query_type": "<type>",
      "agent_name": "<name>",
      "span_count": <int>,
      "hallucination_rate": <float 0.0-1.0>,
      "worst_score": <float 0-10>,
      "sample_trace_ids": ["<id1>", "<id2>", "<id3>"]
    }}
  ],
  "healing_required": <true if any failure_clusters exist, else false>
}}
""",
    tools=[_phoenix_mcp_read],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.0,
    ),
    output_key="detected_patterns",
    disallow_transfer_to_parent=False,
    disallow_transfer_to_peers=True,
)
