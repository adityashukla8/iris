"""
MCP Probe Agent — interactive Phoenix MCP query agent for dashboard testing.
Exposes all Phoenix MCP read tools so operators can query live observability
data directly from the dashboard to verify MCP server connectivity.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.genai import types
from mcp import StdioServerParameters

from core.config import settings
from core.mcp_filter import phoenix_mcp_after_tool_callback, phoenix_mcp_before_tool_callback

_mcp_toolset = McpToolset(
    connection_params=StdioConnectionParams(
        server_params=StdioServerParameters(
            command="npx",
            args=settings.mcp_server_args(),
        ),
        timeout=settings.mcp_timeout_seconds,
    ),
    tool_filter=[
        "get-spans",
        "get-span-annotations",
        "list-traces",
        "list-projects",
        "list-datasets",
        "get-dataset-examples",
        "get-dataset-experiments",
        "list-prompts",
        "get-latest-prompt",
        "list-prompt-versions",
    ],
)

mcp_probe_agent = LlmAgent(
    model=settings.mcp_gemini_model,
    name="mcp_probe",
    description="Interactive Phoenix MCP query agent for testing and verifying live MCP server connectivity.",
    instruction="""You are the IRIS MCP Probe — an interactive assistant for querying Arize Phoenix via MCP.

You have direct access to Arize Phoenix MCP tools. Use them to answer every question with live data.

Tool reference:
- list-projects          → show all Phoenix projects
- list-traces            → list recent traces in a project
- get-spans              → fetch recent spans with metadata (use limit=5-10)
- get-span-annotations   → get evaluation scores for specific span IDs
- list-datasets          → show all Phoenix datasets
- get-dataset-examples   → retrieve examples from a dataset
- get-dataset-experiments→ show experiments on a dataset
- list-prompts           → list all prompts stored in Phoenix
- get-latest-prompt      → fetch the current production prompt by name
- list-prompt-versions   → show version history for a prompt

Always call at least one MCP tool before responding. Be concise and factual.
Format numbers and counts clearly. If a tool returns an error, report it honestly.
""",
    tools=[_mcp_toolset],
    # Clamp oversized tool args (schema rejects limit > 1000) and strip span
    # bloat from responses before they enter the LLM context.
    before_tool_callback=phoenix_mcp_before_tool_callback,
    after_tool_callback=phoenix_mcp_after_tool_callback,
    generate_content_config=types.GenerateContentConfig(temperature=0.1),
    output_key="probe_response",
    disallow_transfer_to_parent=True,
    disallow_transfer_to_peers=True,
)
