"""Search engine port (interface)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from app.domain.search.read_models.search_result import SearchResult
from app.domain.search.value_objects.search_query import SearchQuery


class SearchEngine(ABC):
    @abstractmethod
    def search(self, *, query: SearchQuery, organization_id: str) -> SearchResult: ...
