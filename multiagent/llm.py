from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Any

import requests


def _bool_env(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "enabled"}


def _float_env(value: Any, default: float) -> float:
    if value is None or value == "":
        return default
    return float(value)


def _int_env(value: Any, default: int) -> int:
    if value is None or value == "":
        return default
    return int(value)


def _extract_json_block(raw_text: str) -> dict[str, Any]:
    text = str(raw_text or "").strip()
    if not text:
        raise ValueError("LLM response was empty.")

    if text.startswith("```"):
        lines = text.splitlines()
        if lines:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("LLM response did not contain a JSON object.")
    return json.loads(text[start : end + 1])


def _normalize_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                parts.append(str(item.get("text") or item.get("content") or ""))
            else:
                parts.append(str(item))
        return "\n".join(part for part in parts if part).strip()
    return str(content)


@dataclass(frozen=True)
class LLMRuntimeConfig:
    enabled: bool = False
    provider: str = "disabled"
    model: str = ""
    api_base_url: str = "https://api.openai.com/v1"
    api_key: str | None = None
    timeout_seconds: float = 60.0
    temperature: float = 0.1
    max_tokens: int = 700
    extra_headers: dict[str, str] = field(default_factory=dict)

    def public_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "provider": self.provider,
            "model": self.model,
            "api_base_url": self.api_base_url,
            "timeout_seconds": self.timeout_seconds,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            "has_api_key": bool(self.api_key),
            "extra_header_names": sorted(self.extra_headers.keys()),
        }


def resolve_llm_runtime_config(overrides: dict[str, Any] | None = None) -> LLMRuntimeConfig:
    overrides = overrides or {}
    llm_overrides = dict(overrides.get("llm") or {})

    provider = str(llm_overrides.get("provider") or os.getenv("ASSEMBLY_LLM_PROVIDER") or "disabled").strip().lower()
    api_key = llm_overrides.get("api_key") or os.getenv("ASSEMBLY_LLM_API_KEY")
    enabled = _bool_env(
        llm_overrides.get("enabled", os.getenv("ASSEMBLY_LLM_ENABLED")),
        default=provider in {"mock", "openai_compatible"} and bool(api_key or provider == "mock"),
    )

    extra_headers_raw = llm_overrides.get("extra_headers")
    if extra_headers_raw is None:
        env_headers = os.getenv("ASSEMBLY_LLM_EXTRA_HEADERS")
        extra_headers_raw = json.loads(env_headers) if env_headers else {}

    extra_headers = {str(key): str(value) for key, value in dict(extra_headers_raw or {}).items()}

    return LLMRuntimeConfig(
        enabled=enabled,
        provider=provider if enabled else "disabled",
        model=str(llm_overrides.get("model") or os.getenv("ASSEMBLY_LLM_MODEL") or "").strip(),
        api_base_url=str(llm_overrides.get("api_base_url") or os.getenv("ASSEMBLY_LLM_API_BASE_URL") or "https://api.openai.com/v1").rstrip("/"),
        api_key=str(api_key).strip() if api_key else None,
        timeout_seconds=_float_env(llm_overrides.get("timeout_seconds", os.getenv("ASSEMBLY_LLM_TIMEOUT_SECONDS")), 60.0),
        temperature=_float_env(llm_overrides.get("temperature", os.getenv("ASSEMBLY_LLM_TEMPERATURE")), 0.1),
        max_tokens=_int_env(llm_overrides.get("max_tokens", os.getenv("ASSEMBLY_LLM_MAX_TOKENS")), 700),
        extra_headers=extra_headers,
    )


class StructuredLLMClient:
    def __init__(self, config: LLMRuntimeConfig):
        self.config = config

    @property
    def available(self) -> bool:
        return self.config.enabled and self.config.provider in {"mock", "openai_compatible"}

    @property
    def is_mock(self) -> bool:
        return self.config.enabled and self.config.provider == "mock"

    def _endpoint(self) -> str:
        base = self.config.api_base_url.rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def invoke_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        if not self.available or self.is_mock:
            raise RuntimeError("Structured LLM client is not configured for live HTTP calls.")
        if not self.config.model:
            raise RuntimeError("LLM model is not configured.")
        if not self.config.api_key:
            raise RuntimeError("LLM API key is not configured.")

        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        headers.update(self.config.extra_headers)

        payload = {
            "model": self.config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self.config.temperature if temperature is None else temperature,
            "max_tokens": self.config.max_tokens if max_tokens is None else max_tokens,
        }

        last_error: Exception | None = None
        for include_response_format in (True, False):
            candidate_payload = dict(payload)
            if include_response_format:
                candidate_payload["response_format"] = {"type": "json_object"}
            try:
                response = requests.post(
                    self._endpoint(),
                    headers=headers,
                    json=candidate_payload,
                    timeout=self.config.timeout_seconds,
                )
                response.raise_for_status()
                body = response.json()
                content = _normalize_content(body["choices"][0]["message"]["content"])
                return _extract_json_block(content)
            except Exception as exc:  # pragma: no cover - fallback branch exercised in integration only
                last_error = exc
                continue
        raise RuntimeError(f"LLM invocation failed: {last_error}") from last_error
