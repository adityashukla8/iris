from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class QueryType(str, Enum):
    DRUG_DOSAGE = "drug_dosage"
    DRUG_INTERACTION = "drug_interaction"
    PROCEDURE = "procedure"
    PATIENT_LOOKUP = "patient_lookup"
    PHASE_IDENTIFICATION = "phase_identification"
    ALLERGY_CHECK = "allergy_check"
    LAB_INTERPRETATION = "lab_interpretation"
    GENERAL = "general"


class SurgicalPhase(str, Enum):
    PRE_OP = "pre-op"
    INDUCTION = "induction"
    INCISION = "incision"
    DISSECTION = "dissection"
    PROCEDURE_SPECIFIC = "procedure-specific"
    CLOSURE = "closure"
    POST_OP = "post-op"


class RetrievedContext(BaseModel):
    patient_id: str | None = None
    encounter_id: str | None = None
    medications: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)
    creatinine_clearance: float | None = None  # mL/min
    weight_kg: float | None = None
    age_years: int | None = None
    diagnoses: list[str] = Field(default_factory=list)
    lab_results: dict[str, Any] = Field(default_factory=dict)
    surgical_history: list[str] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict)


class ToolCall(BaseModel):
    tool: str
    input: str | dict[str, Any]
    output: str | dict[str, Any] | None = None
    latency_ms: int | None = None


class Severity(str, Enum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class EvalResult(BaseModel):
    evaluator: str
    score: float = Field(ge=0.0, le=10.0)
    severity: Severity
    passed: bool
    rationale: str
    flagged_claims: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    reasoning_chain: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)

    @classmethod
    def from_score(cls, evaluator: str, score: float, rationale: str, **kwargs: Any) -> EvalResult:
        if score >= 7.0:
            severity, passed = Severity.INFO, True
        elif score >= 5.0:
            severity, passed = Severity.WARNING, False
        else:
            severity, passed = Severity.CRITICAL, False
        return cls(evaluator=evaluator, score=score, severity=severity, passed=passed,
                   rationale=rationale, **kwargs)


class IrisEvent(BaseModel):
    agent_name: str
    agent_version: str = "unknown"
    trace_id: str = Field(default_factory=lambda: str(uuid4()))
    session_id: str = Field(default_factory=lambda: str(uuid4()))
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    query_type: QueryType = QueryType.GENERAL
    input_prompt: str
    retrieved_context: RetrievedContext = Field(default_factory=RetrievedContext)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    output_text: str
    surgical_phase: SurgicalPhase | None = None
    latency_ms: int | None = None
    token_count: int | None = None

    model_config = {"use_enum_values": True}


class SelfHealEvent(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    agent_name: str
    query_type: str
    failure_cluster_size: int
    hallucination_rate_before: float
    hallucination_rate_after: float | None = None
    prompt_diff: str | None = None
    dataset_id: str | None = None
    experiment_id: str | None = None
    validated: bool = False
    actions_taken: list[str] = Field(default_factory=list)


class AlertEvent(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    severity: Severity
    agent_name: str
    trace_id: str
    query_type: str
    failure_type: str
    description: str
    eval_score: float | None = None
