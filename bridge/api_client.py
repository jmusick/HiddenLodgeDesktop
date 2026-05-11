"""HTTP client for the HiddenLodge website API."""

from __future__ import annotations

import time

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
        self._timeout = httpx.Timeout(
            connect=config.api_connect_timeout_seconds,
            read=config.api_read_timeout_seconds,
            write=config.api_write_timeout_seconds,
            pool=config.api_connect_timeout_seconds,
        )
        self._retries = config.api_request_retries
        self._retry_backoff_seconds = config.api_retry_backoff_seconds

    def _url(self, path: str) -> str:
        return f"{self._base}{path}"

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        attempts = self._retries + 1
        last_exc: httpx.RequestError | None = None

        for attempt in range(attempts):
            try:
                with httpx.Client(headers=self._headers, timeout=self._timeout) as client:
                    response = client.request(method, self._url(path), **kwargs)
                    response.raise_for_status()
                    return response
            except httpx.HTTPStatusError:
                raise
            except httpx.RequestError as exc:
                last_exc = exc
                if attempt >= attempts - 1:
                    break
                time.sleep(self._retry_backoff_seconds * (attempt + 1))

        if isinstance(last_exc, httpx.ReadTimeout):
            raise RuntimeError(
                f"Read timeout calling {path} after {attempts} attempt(s). "
                f"Increase api_read_timeout_seconds in config.json if needed."
            ) from last_exc
        if last_exc is not None:
            raise RuntimeError(f"Request failed calling {path} after {attempts} attempt(s): {last_exc}") from last_exc
        raise RuntimeError(f"Request failed calling {path}: unknown error")

    def get(self, path: str, **kwargs) -> httpx.Response:
        return self._request("GET", path, **kwargs)

    def post(self, path: str, payload: dict, **kwargs) -> httpx.Response:
        return self._request("POST", path, json=payload, **kwargs)
