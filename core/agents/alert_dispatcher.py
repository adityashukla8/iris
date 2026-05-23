"""
Alert Dispatcher — ADK LlmAgent.
Routes safety events by severity to the dashboard and (future) TTS.
"""
from __future__ import annotations

from google.adk.agents import LlmAgent
from google.genai import types

from core.agents.tools.eval_tools import push_dashboard_alert
from core.config import settings

alert_dispatcher_agent = LlmAgent(
    model=settings.gemini_model,
    name="alert_dispatcher",
    description=(
        "Routes clinical safety alerts by severity to the correct output channels. "
        "Use this agent after safety evaluation to dispatch alerts to the OR dashboard. "
        "INFO events → dashboard feed only. WARNING → yellow badge. CRITICAL → red badge + human escalation."
    ),
    instruction="""You are the IRIS Alert Dispatcher — the notification routing layer.

You receive a safety evaluation summary and dispatch alerts appropriately.

Routing rules:
- severity=info → call push_dashboard_alert (for dashboard live feed visibility only)
- severity=warning → call push_dashboard_alert with warning severity
- severity=critical → call push_dashboard_alert with critical severity

For CRITICAL alerts, the description must follow this format:
"IRIS: <failure_type> detected in <agent_name> <query_type>. Human review required."
(replace angle-bracket placeholders with the actual values from the alert)

After dispatching, output a JSON object with these keys:
  dispatched: true or false
  severity: the severity string
  channel: "dashboard"
  alert_description: the description string you sent
""",
    tools=[push_dashboard_alert],
    generate_content_config=types.GenerateContentConfig(
        temperature=0.0,
    ),
    output_key="alert_dispatch_result",
    disallow_transfer_to_parent=False,
    disallow_transfer_to_peers=True,
)
