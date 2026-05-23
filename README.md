# IRIS — Inference Risk and Integrity Supervisor

**An autonomous multi-agent clinical AI safety supervisor built on Google ADK + Arize Phoenix.**

IRIS watches every output from clinical AI agents in real time, runs five specialized safety evaluations, detects failure patterns across a shift, and autonomously rewrites the agent's prompt to prevent recurrence — all without human intervention.

> Built for the Google Cloud Rapid Agent Hackathon (Arize Phoenix Track)

---

## What IRIS Does

```
Clinical AI Agent (ORION)
        │ IrisEvent (POST /event)
        ▼
┌─────────────────────────────────────────────────────────┐
│                    IRIS Supervisor                       │
│                                                         │
│  Orchestrator (ADK LlmAgent)                            │
│       │                                                 │
│       ├──▶ Safety Evaluator ──▶ 5 Evaluators:           │
│       │        ├── Factual Hallucination (RxNorm+LLM)   │
│       │        ├── Dosage Boundary (OpenFDA+LLM)        │
│       │        ├── Attribution (cross-patient check)    │
│       │        ├── Context Gap (missing patient vars)   │
│       │        └── Surgical Phase (phase consistency)   │
│       │              │                                  │
│       │         Phoenix OTel ──▶ Arize Phoenix Cloud    │
│       │                                                 │
│       ├──▶ Pattern Detector ──▶ Phoenix MCP get-spans   │
│       │        │ failure cluster detected               │
│       ▼        ▼                                        │
│    Alert ◀── Self-Healer ──▶ Phoenix MCP upsert-prompt  │
│  Dispatcher        │  (autonomous prompt mutation)      │
│       │            └──▶ Phoenix dataset + experiment    │
│       ▼                                                 │
│  OR Dashboard (SSE live feed)                           │
└─────────────────────────────────────────────────────────┘
```

---

## Quickstart

```bash
# 1. Clone and set up environment
git clone <repo>
cd iris
conda create -n iris python=3.11 -y && conda activate iris
pip install -e ".[dev]"

# 2. Configure credentials
cp .env.example .env
# Edit .env: GOOGLE_API_KEY, PHOENIX_API_KEY, PHOENIX_CLIENT_URL

# 3. Start IRIS
uvicorn core.main:app --port 8080 --reload

# 4. Open dashboard
open http://localhost:8080/

# 5. Run demo scenarios (5 clinical failure scenarios)
python demo/mock_agents/bad_orion.py --url http://localhost:8080
```

---

## Integration Contract

Any clinical AI agent integrates with IRIS in under 10 lines:

```python
from sdk.client import IrisClient
from sdk.models import IrisEvent, QueryType

async with IrisClient("http://iris.internal:8080") as iris:
    result = await iris.submit(IrisEvent(
        agent_name="ORION",
        query_type=QueryType.DRUG_DOSAGE,
        input_prompt=user_query,
        output_text=agent_response,
        retrieved_context={"patient_id": "PT-001", "creatinine_clearance": 34.1, ...},
    ))

    if result.get("severity") == "critical":
        halt_and_escalate()
```

Or for agents that don't import the SDK:

```bash
curl -X POST http://iris.internal:8080/event \
  -H "Content-Type: application/json" \
  -d '{
    "agent_name": "ORION",
    "query_type": "drug_dosage",
    "input_prompt": "What dose of vancomycin?",
    "output_text": "Vancomycin 8000mg IV...",
    "retrieved_context": {"patient_id": "PT-001", "creatinine_clearance": 34.1}
  }'
```

---

## Evaluators

| Evaluator | What It Catches | Query Types | Knowledge Source |
|-----------|----------------|-------------|-----------------|
| **Factual Hallucination** | Drug names not in RxNorm, invented procedures, impossible values | All | RxNorm API + Gemini LLM Judge |
| **Dosage Boundary** | Doses outside FDA-approved range, missing renal adjustment | `drug_dosage`, `drug_interaction` | OpenFDA API + Gemini LLM Judge |
| **Attribution** | Cross-patient data contamination, claims not traceable to patient record | All (with patient context) | Gemini LLM Judge |
| **Context Gap** | Clinical questions answered without required patient variables | All | Gemini (dynamic inference, no hardcoded tables) |
| **Surgical Phase** | Recommendations inappropriate for current surgical phase | All (when `surgical_phase` present) | Gemini LLM Judge |

All evaluators return a standard `EvalResult`:
```json
{
  "evaluator": "dosage_boundary",
  "score": 1.5,
  "severity": "critical",
  "passed": false,
  "rationale": "Vancomycin 8000mg exceeds FDA max. CKD patient requires 50% dose reduction.",
  "flagged_claims": ["vancomycin 8000mg exceeds recommended maximum of 4000mg/day"],
  "metadata": {"llm_judged": true, "drug_mentions": 1}
}
```

---

## Self-Healing (Hackathon Differentiator)

When the Pattern Detector identifies ≥5 failures of the same type from the same agent, the Self-Healer executes a 9-step autonomous repair sequence via Arize Phoenix MCP:

1. **Retrieve** the 10 worst-scoring spans via `get-spans`
2. **Confirm** scores via `get-span-annotations`
3. **Log** 5 failure examples to Phoenix dataset (`add-dataset-examples`)
4. **Check** prior experiments for recent healing attempts
5. **Read** the current active prompt via `get-latest-prompt`
6. **Construct** a targeted constraint for the failure type
7. **Write** the new prompt version via `upsert-prompt`
8. **Record** the healing event to dashboard + shift report
9. **Validate** improvement after the next 10 spans arrive

The injected constraints are failure-specific, not generic:
- Drug dosage failures → `"CRITICAL: Always verify stated dose against FDA maximum daily dose."`
- Hallucination failures → `"CRITICAL: Only state drug names that exist in RxNorm. Verify before every mention."`
- Context gap failures → `"CRITICAL: Before answering dosage questions, confirm creatinine_clearance is present."`

---

## Arize Phoenix Observability

Every evaluation result is written to Arize Phoenix Cloud via two paths:

1. **OTel span attributes** (primary): written as `iris.eval.{evaluator}.score`, `.severity`, `.passed`, `.rationale` on the ADK span — always fires
2. **REST span annotations** (secondary): structured annotations via `/v1/span_annotations` — best-effort

View traces at: `https://app.phoenix.arize.com/s/<your-space>/projects/iris-clinical`

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/event` | Submit an IrisEvent for evaluation |
| `GET` | `/stream/alerts` | SSE stream of live safety alerts |
| `GET` | `/status` | Shift stats (traces, alerts, self-heals) |
| `GET` | `/traces` | Recent trace feed (last 200) |
| `POST` | `/scan` | Trigger immediate pattern scan |
| `GET` | `/` | OR dashboard (live feed) |

---

## Project Structure

```
iris/
├── sdk/
│   ├── models.py          # IrisEvent, EvalResult, AlertEvent (Pydantic v2)
│   └── client.py          # IrisClient — async HTTP client for agents
├── core/
│   ├── agents/
│   │   ├── orchestrator.py       # Root ADK LlmAgent
│   │   ├── safety_evaluator.py   # Runs all 5 evaluators
│   │   ├── pattern_detector.py   # Phoenix MCP read tools
│   │   ├── self_healer.py        # Phoenix MCP write tools (9-step)
│   │   ├── alert_dispatcher.py   # Routes alerts to dashboard
│   │   └── tools/eval_tools.py   # ADK function tools wrapping evaluators
│   ├── evaluators/
│   │   ├── base.py               # EvalPlugin ABC
│   │   ├── factual_hallucination.py
│   │   ├── dosage_boundary.py
│   │   ├── attribution.py
│   │   ├── context_gap.py
│   │   └── surgical_phase.py
│   ├── knowledge/
│   │   ├── rxnorm.py      # RxNorm API + LLM drug extraction
│   │   └── fda_labels.py  # OpenFDA label client (cached)
│   ├── phoenix/
│   │   └── client.py      # Dual-path span annotation
│   ├── config.py
│   ├── state.py           # In-process alert bus + shift stats
│   └── main.py            # FastAPI app + OTel registration
├── dashboard/
│   └── templates/         # Jinja2 + HTMX, dark OR-ambient theme
├── demo/
│   ├── mock_agents/bad_orion.py  # 5 clinical failure scenarios
│   └── patients/                 # 3 synthetic FHIR patients
├── tests/
│   ├── test_evaluators.py
│   └── test_pipeline.py
├── pyproject.toml
└── Dockerfile
```

---

## Environment Variables

```env
GOOGLE_API_KEY=...          # Gemini 2.5 Pro API key
PHOENIX_API_KEY=...         # Arize Phoenix system key (JWT)
PHOENIX_CLIENT_URL=...      # https://app.phoenix.arize.com/s/<space>
IRIS_PORT=8080
IRIS_ENV=development
```

---

## Running Tests

```bash
# Unit tests (evaluators — requires GOOGLE_API_KEY)
pytest tests/test_evaluators.py -v --asyncio-mode=auto

# Integration tests (full pipeline)
pytest tests/test_pipeline.py -v

# All tests
pytest tests/ -v --asyncio-mode=auto
```

---

## Deploying to Cloud Run

```bash
gcloud run deploy iris \
  --source . \
  --region us-central1 \
  --port 8080 \
  --set-env-vars GOOGLE_API_KEY=${GOOGLE_API_KEY},PHOENIX_API_KEY=${PHOENIX_API_KEY},PHOENIX_CLIENT_URL=${PHOENIX_CLIENT_URL} \
  --allow-unauthenticated
```

---

## License

Apache 2.0 — see [LICENSE](LICENSE)
