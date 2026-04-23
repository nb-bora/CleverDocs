"""Semantic search (embeddings) + hybrid ranking utilities.

Design goals:
- Works in dev with SQLite (no external vector DB).
- Portable schema (embedding stored as JSON text).
- "Best possible" relevance for MVP: semantic retrieval + optional lexical fusion.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import lru_cache

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.infrastructure.db.orm.models.document_embedding_model import DocumentEmbeddingModel


def _try_import_embedder():
    try:
        from sentence_transformers import SentenceTransformer  # type: ignore

        return SentenceTransformer
    except Exception:  # pragma: no cover
        return None


@lru_cache(maxsize=4)
def _get_embedder(model_name: str):
    sentence_transformer_cls = _try_import_embedder()
    if sentence_transformer_cls is None:
        raise RuntimeError("sentence-transformers not installed")
    # Cache per-process: huge latency win vs re-loading per request.
    return sentence_transformer_cls(model_name)


@dataclass(frozen=True)
class SemanticSettings:
    model_name: str
    chunk_chars: int = 1200
    chunk_overlap_chars: int = 200
    max_chunks_per_doc: int = 64


def chunk_text(*, text: str, chunk_chars: int, chunk_overlap_chars: int, max_chunks: int) -> list[str]:
    t = (text or "").strip()
    if not t:
        return []
    chunk_chars = max(200, int(chunk_chars))
    overlap = max(0, min(int(chunk_overlap_chars), chunk_chars - 50))

    out: list[str] = []
    i = 0
    n = len(t)
    while i < n and len(out) < max_chunks:
        j = min(n, i + chunk_chars)
        out.append(t[i:j])
        if j >= n:
            break
        i = max(0, j - overlap)
    return out


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return -1.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return -1.0
    return dot / (math.sqrt(na) * math.sqrt(nb))


def embed_texts(*, model_name: str, texts: list[str]) -> list[list[float]]:
    model = _get_embedder(model_name)
    vecs = model.encode(texts, normalize_embeddings=False)  # returns numpy array
    # Convert to plain python lists for storage/compat.
    return [list(map(float, v)) for v in vecs]


def upsert_document_embeddings(
    *,
    db: Session,
    organization_id: str,
    document_id: str,
    content: str,
    settings: SemanticSettings,
) -> None:
    chunks = chunk_text(
        text=content,
        chunk_chars=settings.chunk_chars,
        chunk_overlap_chars=settings.chunk_overlap_chars,
        max_chunks=settings.max_chunks_per_doc,
    )
    if not chunks:
        # If no text, clear embeddings (keeps index consistent with content lifecycle).
        db.execute(delete(DocumentEmbeddingModel).where(DocumentEmbeddingModel.document_id == document_id))
        return

    vectors = embed_texts(model_name=settings.model_name, texts=chunks)

    # Simplest + correct: delete old, insert new.
    db.execute(delete(DocumentEmbeddingModel).where(DocumentEmbeddingModel.document_id == document_id))
    for idx, (ch, vec) in enumerate(zip(chunks, vectors)):
        db.add(
            DocumentEmbeddingModel(
                organization_id=organization_id,
                document_id=document_id,
                chunk_index=idx,
                chunk_text=ch,
                embedding_json=json.dumps(vec),
                model_name=settings.model_name,
            )
        )


@dataclass(frozen=True)
class SemanticHit:
    document_id: str
    filename: str
    score: float
    preview: str | None


@dataclass(frozen=True)
class SemanticChunkHit:
    document_id: str
    chunk_index: int
    score: float
    chunk_text: str


def semantic_search_chunks(
    *,
    db: Session,
    organization_id: str,
    query: str,
    settings: SemanticSettings,
    candidate_document_ids: list[str] | None = None,
    limit_docs: int = 25,
    limit_chunks_scan: int = 4000,
) -> list[tuple[str, float, str | None]]:
    """Return per-document best semantic match: (document_id, score, preview)."""

    qvec = embed_texts(model_name=settings.model_name, texts=[query])[0]

    stmt = select(
        DocumentEmbeddingModel.document_id,
        DocumentEmbeddingModel.chunk_text,
        DocumentEmbeddingModel.embedding_json,
    ).where(DocumentEmbeddingModel.organization_id == organization_id)

    if candidate_document_ids:
        stmt = stmt.where(DocumentEmbeddingModel.document_id.in_(candidate_document_ids))

    rows = db.execute(stmt.limit(int(limit_chunks_scan))).all()

    best: dict[str, tuple[float, str | None]] = {}
    for doc_id, chunk_text, emb_json in rows:
        try:
            vec = json.loads(emb_json)
            if not isinstance(vec, list):
                continue
            score = _cosine(qvec, [float(x) for x in vec])
        except Exception:
            continue
        cur = best.get(str(doc_id))
        if cur is None or score > cur[0]:
            preview = (chunk_text or "").strip()
            if preview:
                preview = preview[:600]
            best[str(doc_id)] = (float(score), preview or None)

    ranked = sorted(best.items(), key=lambda kv: kv[1][0], reverse=True)[: int(limit_docs)]
    return [(doc_id, sc, prev) for doc_id, (sc, prev) in ranked]


def semantic_search_top_chunks(
    *,
    db: Session,
    organization_id: str,
    query: str,
    settings: SemanticSettings,
    candidate_document_ids: list[str] | None = None,
    limit_chunks: int = 12,
    limit_chunks_scan: int = 6000,
) -> list[SemanticChunkHit]:
    """Return top chunks across candidate docs: (doc_id, chunk_index, score, chunk_text)."""

    qvec = embed_texts(model_name=settings.model_name, texts=[query])[0]

    stmt = select(
        DocumentEmbeddingModel.document_id,
        DocumentEmbeddingModel.chunk_index,
        DocumentEmbeddingModel.chunk_text,
        DocumentEmbeddingModel.embedding_json,
    ).where(DocumentEmbeddingModel.organization_id == organization_id)

    if candidate_document_ids:
        stmt = stmt.where(DocumentEmbeddingModel.document_id.in_(candidate_document_ids))

    rows = db.execute(stmt.limit(int(limit_chunks_scan))).all()

    hits: list[SemanticChunkHit] = []
    for doc_id, chunk_index, chunk_text, emb_json in rows:
        try:
            vec = json.loads(emb_json)
            if not isinstance(vec, list):
                continue
            score = _cosine(qvec, [float(x) for x in vec])
        except Exception:
            continue
        txt = (chunk_text or "").strip()
        if not txt:
            continue
        hits.append(
            SemanticChunkHit(
                document_id=str(doc_id),
                chunk_index=int(chunk_index),
                score=float(score),
                chunk_text=txt[:1800],  # keep payload small
            )
        )

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[: int(limit_chunks)]


def rrf_fuse(*, ranked_lists: list[list[str]], k: int = 60, limit: int = 25) -> list[str]:
    """Reciprocal Rank Fusion over doc_id ranked lists."""
    scores: dict[str, float] = {}
    for lst in ranked_lists:
        for rank, doc_id in enumerate(lst, start=1):
            scores[doc_id] = scores.get(doc_id, 0.0) + 1.0 / (k + rank)
    return [doc_id for doc_id, _ in sorted(scores.items(), key=lambda kv: kv[1], reverse=True)[:limit]]

