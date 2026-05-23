"""
Self-Healer — ADK LlmAgent with Arize Phoenix MCP tools.

DIAGNOSE phase only. This agent:
  1. Reads the worst-scoring spans from the failure cluster via Phoenix MCP
  2. Retrieves the current clinical safety prompt from Phoenix
  3. Logs the failure examples to a Phoenix dataset for tracking
  4. Produces a structured HealingDiagnosis JSON with failure analysis

The GENERATE → VALIDATE → GATE → DEPLOY phases are handled by the Python pipeline
in core/healing/pipeline.py, which is triggered by the orchestrator after this
agent outputs a HealingDiagnosis.

Architecture note: Prompt mutation and deployment are NOT done here because:
  - MCP `upsert-prompt` always creates new top-level prompts (not versions)
  - MCP cannot run Phoenix experiments (that's Python-only)
  - Human approval gate must be enforced before any prompt reaches production
  - The mutation engine requires Python async concurrency (not possible in MCP tool calls)

MCP tools used (confirmed against @arizeai/phoenix-mcp v4.0.8 source):
  - get-spans: retrieve spans by filter
  - get-span-annotations: retrieve eval annotations for span IDs
  - add-dataset-examples: log failure examples to Phoenix dataset
  - get-dataset-examples: verify examples were logged correctly (confirm step)
  - list-datasets: verify dataset existence before adding examples
  - get-dataset-experiments: check prior healing experiments on this dataset
  - get-latest-prompt: retrieve current production prompt text
  - list-prompts: enumerate available prompts
  - list-prompt-versions: show full version history for the healing prompt
  - add-prompt-version-tag: tag prompt versions via MCP (e.g., 'candidate', 'rollback')

Intentionally excluded:
  - upsert-prompt: creates new top-level prompts, not versions — REST API handles versioning
"""
from __future__ import annotations

from google.adk.agents import LlmAgent
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.tools.mcp_tool.mcp_toolset import McpToolset
from google.genai import types
from mcp import StdioServerParameters

from core.config import settings

_phoenix_mcp = McpToolset(
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
        timeout=60.0,
    ),
    tool_filter=[
        "get-spans",
        "get-span-annotations",
        "add-dataset-examples",
        "get-dataset-examples",      # verify examples logged correctly after add
        "list-datasets",
        "get-dataset-experiments",   # correct tool name (not list-experiments-for-dataset)
        "get-latest-prompt",
        "list-prompts",
        "list-prompt-versions",      # show full version history for audit trail
        "add-prompt-version-tag",    # tag prompt versions via MCP (candidate/rollback)
    ],
)

_HEALING_PROMPT_NAME = settings.healing_prompt_name

self_healer_agent = LlmAgent(
    model=settings.gemini_model,
    name="self_healer",
    description=(
        "DIAGNOSE phase of the IRIS self-healing loop. "
        "Invoked when a clinical safety failure cluster is detected. "
        "Reads the worst-performing spans from Phoenix, analyzes the failure pattern, "
        "logs failure examples to a labeled dataset, and outputs a HealingDiagnosis "
        "that the Python pipeline uses for prompt mutation and validation."
    ),
    instruction=f"""You are the IRIS Self-Healer — DIAGNOSE phase.

You are invoked with a failure_cluster JSON from the Pattern Detector.
Your job is to deeply understand the failure pattern and produce a HealingDiagnosis
that the Python pipeline will use to generate and validate a candidate prompt mutation.

You do NOT mutate prompts. You do NOT call upsert-prompt. You DIAGNOSE.

Execute these steps precisely:

Step 1 — Retrieve worst-performing spans:
  Use `get-spans` to retrieve the 10 worst-scoring spans from the failure cluster.
  Filter by the query_type and agent_name from the failure_cluster JSON.
  Request spans from the last {settings.pattern_window_minutes} minutes.

Step 2 — Confirm safety evaluation scores:
  Use `get-span-annotations` on the retrieved span IDs to confirm their IRIS
  safety evaluation scores. Record the 5 lowest-scoring spans — these are your
  failure examples with the most signal.

Step 3 — Retrieve the current clinical AI prompt and version history:
  Use `list-prompts` to find the prompt named "{_HEALING_PROMPT_NAME}".
  If found, use `get-latest-prompt` with prompt_identifier="{_HEALING_PROMPT_NAME}"
  to retrieve its current text and version.
  Also use `list-prompt-versions` to retrieve the full version history —
  note how many versions exist and when the most recent was created.
  If not found, use the empty string "" as current_prompt_text and note the absence.

Step 4 — Log failure examples to Phoenix dataset:
  The dataset name is: "iris-failures-{{query_type}}" (replace {{query_type}} with the actual type).
  Use `add-dataset-examples` to add up to 5 failure examples.
  Each example format:
  {{
    "input": {{
      "query_type": "<type>",
      "input_prompt": "<the clinical question from the span>",
      "output_text": "<the unsafe AI response from the span>"
    }},
    "output": {{
      "expected": "Safe, grounded clinical response that would pass all IRIS evaluators"
    }},
    "metadata": {{
      "iris_score": <float>,
      "failure_type": "<type>",
      "agent_name": "<name>",
      "span_id": "<id>"
    }}
  }}
  After adding examples, use `get-dataset-examples` to verify they were logged correctly.
  Report how many examples are now in the dataset.

Step 5 — Check for recent healing attempts:
  Use `get-dataset-experiments` with dataset_name="iris-failures-{{query_type}}"
  to check if a healing experiment ran in the last 2 hours.
  If yes, note it in the diagnosis.

Step 6 — Produce failure analysis (the textual gradient seed):
  Based on everything you observed, write a precise failure analysis:
  - What type of clinical error is occurring?
  - What specific constraint or instruction is missing from the current prompt?
  - What patient safety risk does this create?
  Keep this to 2-4 sentences — it seeds the TextGrad mutation engine.

Output ONLY valid JSON matching this schema exactly:
{{
  "candidate_id": "<generate a UUID>",
  "failure_cluster": {{<the original failure_cluster object from Pattern Detector>}},
  "query_type": "<from failure_cluster>",
  "agent_name": "<from failure_cluster>",
  "failing_span_ids": ["<span_id_1>", "<span_id_2>", ...],
  "hallucination_rate": <float 0.0-1.0, from failure_cluster>,
  "current_prompt_name": "{_HEALING_PROMPT_NAME}",
  "current_prompt_text": "<prompt text from get-latest-prompt, or empty string>",
  "current_prompt_version": "<version string or null>",
  "prompt_version_count": <int, total versions from list-prompt-versions, or 0>,
  "dataset_name": "iris-failures-{{query_type}}",
  "examples_logged": <int, number of examples added to dataset>,
  "dataset_total_examples": <int, total examples in dataset after add, from get-dataset-examples>,
  "failure_analysis": "<2-4 sentence analysis of the root cause and missing constraint>",
  "prior_experiment_found": <true/false>,
  "timestamp": "<ISO8601 UTC>"
}}

If any step fails, continue with what you have and set the affected fields to null or empty.
Do not abort the entire diagnosis if a single step fails.
""",
    tools=[_phoenix_mcp],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.1,
    ),
    output_key="healing_diagnosis",
    disallow_transfer_to_parent=False,
    disallow_transfer_to_peers=True,
)
