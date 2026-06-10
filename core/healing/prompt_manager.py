"""
Phoenix prompt versioning via REST API.

The MCP `upsert-prompt` tool always creates new top-level prompt objects (not versions
of an existing prompt) — confirmed from the @arizeai/phoenix-mcp source code.
Proper prompt versioning (creating a new version under an existing prompt name,
tagging versions as 'production' or 'candidate') requires the REST API directly.

REST endpoints used:
  POST /v1/prompts                              → create prompt or new version
  GET  /v1/prompts/{prompt_identifier}          → get latest version by name
  POST /v1/prompt_versions/{id}/tags            → tag a version
"""
from __future__ import annotations

import json

import httpx

from core.config import settings


class PhoenixPromptManager:
    def __init__(self) -> None:
        self._base = settings.phoenix_api_url
        self._headers = {
            "Authorization": f"Bearer {settings.phoenix_api_key}",
            "Content-Type": "application/json",
        }

    async def get_prompt(self, prompt_name: str) -> dict | None:
        """
        Retrieve the latest version of a named prompt from Phoenix.
        Returns the prompt version dict, or None if not found.
        """
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(
                    f"{self._base}/v1/prompts/{prompt_name}",
                    headers=self._headers,
                )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                content_type = resp.headers.get("content-type", "")
                if "text/html" in content_type:
                    print(f"[PromptManager] '{prompt_name}' not in Phoenix yet (HTML response — prompt will be created on first heal)")
                    return None
                try:
                    return resp.json()
                except (json.JSONDecodeError, ValueError) as je:
                    print(f"[PromptManager] get_prompt non-JSON body ({resp.status_code}): {je}")
                    return None
        except httpx.HTTPError as exc:
            print(f"[PromptManager] get_prompt failed: {exc}")
            return None

    async def create_prompt_version(
        self,
        prompt_name: str,
        template: str,
        description: str = "",
        model_provider: str = "GOOGLE",
        model_name: str | None = None,
        temperature: float = 0.1,
    ) -> dict | None:
        """
        Create a new version under the named prompt.
        Phoenix automatically creates the prompt object if it doesn't exist,
        or adds a new version to the existing prompt.

        Returns the created prompt version dict including version_id.
        """
        payload = {
            "prompt": {
                "name": prompt_name,
                "description": description or f"IRIS auto-generated — {prompt_name}",
            },
            "version": {
                "description": description,
                "model_provider": model_provider,
                "model_name": model_name or settings.gemini_model,
                "template": {
                    "type": "chat",
                    "messages": [{"role": "user", "content": template}],
                },
                "template_type": "CHAT",
                "template_format": "MUSTACHE",
                "invocation_parameters": {
                    "type": "google",
                    "google": {"temperature": temperature},
                },
            },
        }
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    f"{self._base}/v1/prompts",
                    json=payload,
                    headers=self._headers,
                )
                resp.raise_for_status()
                try:
                    return resp.json()
                except (json.JSONDecodeError, ValueError) as je:
                    print(f"[PromptManager] create_prompt_version non-JSON body ({resp.status_code}): {resp.text[:100]!r} — {je}")
                    return None
        except httpx.HTTPStatusError as exc:
            msg = f"[PromptManager] {exc.response.status_code} on POST /v1/prompts: {exc.response.text[:200]}"
            print(msg)
            from core.state import push_activity
            push_activity(f"Healing: prompt write failed HTTP {exc.response.status_code} — {exc.response.text[:80]}", "warn")
            return None
        except httpx.HTTPError as exc:
            print(f"[PromptManager] create_prompt_version transport error: {exc}")
            return None

    async def tag_prompt_version(self, version_id: str, tag: str) -> bool:
        """
        Tag a specific prompt version (e.g., 'production', 'candidate', 'rollback').
        Tags are used to identify the active production prompt.
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{self._base}/v1/prompt_versions/{version_id}/tags",
                    json={"name": tag},
                    headers=self._headers,
                )
                resp.raise_for_status()
                return True
        except httpx.HTTPError as exc:
            print(f"[PromptManager] tag_prompt_version failed: {exc}")
            return False

    async def get_prompt_by_tag(self, prompt_name: str, tag: str) -> dict | None:
        """
        Retrieve a specific tagged version of a prompt (e.g., the 'production' version).
        """
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(
                    f"{self._base}/v1/prompts/{prompt_name}/tags/{tag}",
                    headers=self._headers,
                )
                if resp.status_code == 404:
                    return None
                resp.raise_for_status()
                try:
                    return resp.json()
                except (json.JSONDecodeError, ValueError) as je:
                    print(f"[PromptManager] get_prompt_by_tag non-JSON body: {resp.text[:100]!r} — {je}")
                    return None
        except httpx.HTTPError as exc:
            print(f"[PromptManager] get_prompt_by_tag failed: {exc}")
            return None


prompt_manager = PhoenixPromptManager()
