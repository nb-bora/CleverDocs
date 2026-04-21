"""OpenSearch/Elasticsearch client wrapper (MVP).

This is a tiny HTTP wrapper using `httpx`. It works with OpenSearch and ES-compatible APIs.
Later phases can replace this with the official client without changing the domain/application.
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx


class OpenSearchError(RuntimeError):
    pass


@dataclass(frozen=True)
class OpenSearchConfig:
    base_url: str


class OpenSearchClient:
    def __init__(self, config: OpenSearchConfig) -> None:
        self._base_url = config.base_url.rstrip("/")

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self._base_url + path

    def ping(self, timeout_s: float = 2.0) -> bool:
        try:
            r = httpx.get(self._url("/"), timeout=timeout_s)
            return 200 <= r.status_code < 500
        except Exception:
            return False

    def ensure_index(self, index: str, mapping: dict) -> None:
        # Create index if missing
        r = httpx.head(self._url(f"/{index}"), timeout=5.0)
        if r.status_code == 200:
            return
        if r.status_code not in (404,):
            raise OpenSearchError(f"HEAD index failed ({r.status_code}): {r.text}")

        r = httpx.put(self._url(f"/{index}"), json=mapping, timeout=10.0)
        if r.status_code not in (200, 201):
            raise OpenSearchError(f"Create index failed ({r.status_code}): {r.text}")

    def index_document(self, index: str, doc_id: str, body: dict) -> None:
        r = httpx.put(self._url(f"/{index}/_doc/{doc_id}"), json=body, timeout=10.0)
        if r.status_code not in (200, 201):
            raise OpenSearchError(f"Index doc failed ({r.status_code}): {r.text}")

    def search(self, index: str, query: dict) -> dict:
        r = httpx.post(self._url(f"/{index}/_search"), json=query, timeout=10.0)
        if r.status_code != 200:
            raise OpenSearchError(f"Search failed ({r.status_code}): {r.text}")
        return r.json()
