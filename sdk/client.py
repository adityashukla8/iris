"""
IRIS SDK Client — drop-in integration for clinical AI agents.

Any agent that submits outputs to IRIS for safety evaluation imports this:

    from iris_sdk import IrisClient, IrisEvent

    async with IrisClient("http://iris.internal:8080") as iris:
        result = await iris.submit(event)
        if result["severity"] == "critical":
            # halt or escalate
            ...

The client is thin by design — IRIS owns all evaluation logic server-side.
"""
from __future__ import annotations

from typing import Any

import httpx

from sdk.models import IrisEvent


class IrisClient:
    """
    Async HTTP client for submitting IrisEvent objects to the IRIS supervisor.

    Supports both typed (IrisEvent) and raw dict/kwargs submission.
    Thread-safe when shared across coroutines; uses a single connection pool.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:8080",
        timeout: float = 60.0,
        api_key: str | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["X-IRIS-API-Key"] = api_key
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=timeout,
            headers=headers,
        )

    async def submit(self, event: IrisEvent) -> dict[str, Any]:
        """
        Submit a typed IrisEvent for evaluation.

        Returns the IRIS evaluation result dict:
          {"trace_id": str, "status": "evaluated", "result": str}
        Raises httpx.HTTPStatusError on 4xx/5xx.
        """
        resp = await self._client.post(
            "/event",
            content=event.model_dump_json(),
        )
        resp.raise_for_status()
        return resp.json()

    async def submit_raw(self, **kwargs: Any) -> dict[str, Any]:
        """
        Submit event fields as keyword arguments — for agents that don't import Pydantic.

        Example:
            result = await iris.submit_raw(
                agent_name="care-advisor-v2",
                input_prompt="...",
                output_text="...",
                query_type="drug_dosage",
                retrieved_context={"patient_id": "PT-001", ...},
            )
        """
        event = IrisEvent(**kwargs)
        return await self.submit(event)

    async def status(self) -> dict[str, Any]:
        """Return current IRIS shift stats."""
        resp = await self._client.get("/status")
        resp.raise_for_status()
        return resp.json()

    async def health(self) -> bool:
        """Return True if IRIS is reachable."""
        try:
            resp = await self._client.get("/status", timeout=5.0)
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> IrisClient:
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()
