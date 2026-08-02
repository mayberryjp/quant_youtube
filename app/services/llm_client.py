from __future__ import annotations

import json

import httpx


class LLMClient:
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        timeout: int = 120,
        max_tokens: int = 4096,
        json_mode: bool = True,
        num_ctx: int = 8192,
        client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_tokens = max_tokens
        self.json_mode = json_mode
        self.num_ctx = num_ctx
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        self.client = client or httpx.Client(timeout=timeout, headers=headers)

    def close(self) -> None:
        self.client.close()

    def complete_json(self, system: str, user: str) -> tuple[dict, dict]:
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self.max_tokens,
            "temperature": 0,
            "options": {"num_ctx": self.num_ctx},
        }
        if self.json_mode:
            body["response_format"] = {"type": "json_object"}
        resp = self.client.post(f"{self.base_url}/chat/completions", json=body)
        resp.raise_for_status()
        payload = resp.json()
        content = payload["choices"][0]["message"]["content"]
        if isinstance(content, dict):
            data = content
        else:
            data = json.loads(content)
        usage = payload.get("usage") or {}
        return data, usage
