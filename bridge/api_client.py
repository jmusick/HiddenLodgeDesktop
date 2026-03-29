"""HTTP client for the HiddenLodge website API."""

from __future__ import annotations

import httpx

from .config import Config


class ApiClient:
    def __init__(self, config: Config) -> None:
        self._base = config.website_url
        self._headers = {
            "X-Desktop-Key": config.api_key,
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        }

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    def get(self, path: str, **kwargs) -> httpx.Response:
        with httpx.Client(headers=self._headers, timeout=10) as client:
            response = client.get(self._url(path), **kwargs)
            response.raise_for_status()
            return response

    def post(self, path: str, payload: dict, **kwargs) -> httpx.Response:
        with httpx.Client(headers=self._headers, timeout=10) as client:
            response = client.post(self._url(path), json=payload, **kwargs)
            response.raise_for_status()
            return response
