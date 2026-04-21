"""Search engine implementation (OpenSearch/Elasticsearch).

Write-side: index documents (projection)
Read-side: search documents (query)
"""

from __future__ import annotations

from dataclasses import dataclass

from app.infrastructure.search.opensearch_client import OpenSearchClient, OpenSearchConfig


@dataclass(frozen=True)
class SearchEngineSettings:
    opensearch_url: str
    index_prefix: str

    @property
    def documents_index(self) -> str:
        return f"{self.index_prefix}-documents"


class SearchEngineImpl:
    def __init__(self, settings: SearchEngineSettings) -> None:
        self._settings = settings
        self._client = OpenSearchClient(OpenSearchConfig(base_url=settings.opensearch_url))

    def ping(self) -> bool:
        return self._client.ping()

    def ensure_documents_index(self) -> str:
        index = self._settings.documents_index
        mapping = {
            "settings": {
                "index": {"number_of_shards": 1, "number_of_replicas": 0},
                "analysis": {
                    "filter": {
                        "cleverdocs_ascii": {"type": "asciifolding", "preserve_original": True}
                    },
                    "analyzer": {
                        # Accent-insensitive analyzer (ingénieur == ingenieur), keeps original too.
                        "cleverdocs_folded": {"tokenizer": "standard", "filter": ["lowercase", "cleverdocs_ascii"]}
                    },
                },
            },
            "mappings": {
                "properties": {
                    # Multi-tenant field reserved for later. Keep it keyword.
                    "organization_id": {"type": "keyword"},
                    "document_id": {"type": "keyword"},
                    "uploaded_by_user_id": {"type": "keyword"},
                    "filename": {
                        "type": "text",
                        "analyzer": "cleverdocs_folded",
                    },
                    "content": {
                        "type": "text",
                        "analyzer": "cleverdocs_folded",
                    },
                    "created_at": {"type": "date"},
                }
            },
        }
        self._client.ensure_index(index=index, mapping=mapping)
        return index

    def index_document(
        self,
        *,
        document_id: str,
        organization_id: str | None,
        uploaded_by_user_id: str | None,
        filename: str,
        content: str,
        created_at_iso: str,
    ) -> None:
        index = self.ensure_documents_index()
        body = {
            "organization_id": organization_id,
            "document_id": document_id,
            "uploaded_by_user_id": uploaded_by_user_id,
            "filename": filename,
            "content": content,
            "created_at": created_at_iso,
        }
        self._client.index_document(index=index, doc_id=document_id, body=body)

    def search(
        self,
        *,
        q: str,
        organization_id: str | None = None,
        uploaded_by_user_id: str | None = None,
        size: int = 25,
    ) -> dict:
        index = self.ensure_documents_index()

        # Modern "intelligent" query (2026 baseline IR):
        # - BM25 (default) with field boosts
        # - fuzziness for typos
        # - phrase match boost for exact sequences
        # - function_score to slightly boost recency (optional)
        must = [
            {
                "dis_max": {
                    "queries": [
                        {
                            "multi_match": {
                                "query": q,
                                "fields": ["content^2.0", "filename^3.0"],
                                "type": "best_fields",
                                "operator": "and",
                                "fuzziness": "AUTO",
                                "prefix_length": 1,
                            }
                        },
                        {
                            "multi_match": {
                                "query": q,
                                "fields": ["content^4.0", "filename^6.0"],
                                "type": "phrase",
                                "slop": 2,
                            }
                        },
                    ]
                }
            }
        ]
        filt = []
        if organization_id is not None:
            filt.append({"term": {"organization_id": organization_id}})
        if uploaded_by_user_id is not None:
            filt.append({"term": {"uploaded_by_user_id": uploaded_by_user_id}})

        query = {
            "size": size,
            "query": {
                "function_score": {
                    "query": {"bool": {"must": must, "filter": filt}},
                    "boost_mode": "sum",
                    "score_mode": "sum",
                    # Soft recency boost (doesn't dominate).
                    "functions": [{"gauss": {"created_at": {"origin": "now", "scale": "30d", "decay": 0.5}}}],
                }
            },
            "highlight": {
                "fields": {
                    "content": {},
                }
            },
        }
        return self._client.search(index=index, query=query)
