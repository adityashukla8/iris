"""
Integration tests for the IRIS FastAPI pipeline.

Uses FastAPI's TestClient (synchronous) for route-level tests.
These tests hit the real orchestrator via HTTP — set GOOGLE_API_KEY and
PHOENIX_API_KEY in the environment before running.

Run: pytest tests/test_pipeline.py -v
"""
from __future__ import annotations

import json
import uuid

import pytest
from fastapi.testclient import TestClient

from core.main import app

client = TestClient(app)


# ── Payloads ───────────────────────────────────────────────────────────────────

def _clean_payload() -> dict:
    return {
        "agent_name": "ORION-test",
        "agent_version": "1.0.0",
        "trace_id": str(uuid.uuid4()),
        "session_id": "test-session",
        "query_type": "drug_interaction",
        "input_prompt": "Is metformin safe to give before the contrast study?",
        "retrieved_context": {
            "patient_id": "PT-TEST-001",
            "medications": ["metformin 1000mg BD"],
            "allergies": ["penicillin"],
            "creatinine_clearance": 68.2,
            "weight_kg": 74.0,
            "age_years": 58,
            "diagnoses": ["Type 2 diabetes mellitus"],
        },
        "tool_calls": [],
        "output_text": (
            "Metformin should be held 48 hours before IV contrast administration. "
            "The drug should be withheld and restarted 48 hours post-procedure."
        ),
        "surgical_phase": "pre-op",
        "latency_ms": 450,
        "token_count": 112,
    }


def _hallucination_payload() -> dict:
    return {
        "agent_name": "ORION-test",
        "trace_id": str(uuid.uuid4()),
        "query_type": "drug_interaction",
        "input_prompt": "Is cephalexim safe for this patient?",
        "retrieved_context": {
            "patient_id": "PT-TEST-002",
            "allergies": ["penicillin"],
        },
        "output_text": "Cephalexim 500mg can be used with caution given the penicillin allergy.",
    }


# ── Route tests ────────────────────────────────────────────────────────────────

class TestStatusEndpoint:
    def test_returns_connected(self):
        resp = client.get("/status")
        assert resp.status_code == 200
        data = resp.json()
        assert data["connected"] is True
        assert "stats" in data

    def test_stats_have_expected_keys(self):
        resp = client.get("/status")
        stats = resp.json()["stats"]
        assert "total_traces" in stats
        assert "hallucinations_caught" in stats
        assert "self_heals" in stats
        assert "human_escalations" in stats


class TestTracesEndpoint:
    def test_returns_traces_list(self):
        resp = client.get("/traces")
        assert resp.status_code == 200
        assert "traces" in resp.json()
        assert isinstance(resp.json()["traces"], list)

    def test_limit_parameter(self):
        resp = client.get("/traces?limit=5")
        assert resp.status_code == 200
        assert len(resp.json()["traces"]) <= 5


class TestEventEndpoint:
    def test_clean_event_returns_evaluated(self):
        resp = client.post("/event", json=_clean_payload(), timeout=120)
        assert resp.status_code == 200
        data = resp.json()
        assert "trace_id" in data
        assert data["status"] == "evaluated"
        assert "result" in data

    def test_event_increments_total_traces(self):
        before = client.get("/status").json()["stats"]["total_traces"]
        client.post("/event", json=_clean_payload(), timeout=120)
        after = client.get("/status").json()["stats"]["total_traces"]
        assert after == before + 1

    def test_invalid_event_returns_422(self):
        # Missing required fields
        resp = client.post("/event", json={"agent_name": "ORION"})
        assert resp.status_code == 422

    def test_event_trace_id_echoed(self):
        payload = _clean_payload()
        trace_id = payload["trace_id"]
        resp = client.post("/event", json=payload, timeout=120)
        assert resp.status_code == 200
        assert resp.json()["trace_id"] == trace_id

    def test_trace_appears_in_recent_traces(self):
        payload = _clean_payload()
        trace_id = payload["trace_id"]
        client.post("/event", json=payload, timeout=120)
        traces = client.get("/traces").json()["traces"]
        trace_ids = [t["trace_id"] for t in traces]
        assert trace_id in trace_ids


class TestDashboardEndpoint:
    def test_dashboard_returns_html(self):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]


class TestScanEndpoint:
    def test_scan_returns_result(self):
        resp = client.post("/scan", timeout=120)
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        assert data["status"] == "scan_complete"
