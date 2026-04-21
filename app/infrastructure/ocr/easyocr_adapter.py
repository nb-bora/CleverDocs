"""EasyOCR adapter.

Responsibilities:
- Provide a thin, testable wrapper around EasyOCR
- Lazy-load heavy dependencies
- Cache readers to avoid reloading models on every request
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


class EasyOcrNotInstalled(RuntimeError):
    pass


@dataclass(frozen=True)
class EasyOcrSettings:
    languages: tuple[str, ...]
    gpu: bool = False


def _import_easyocr():
    try:
        import easyocr  # type: ignore

        return easyocr
    except Exception as e:  # pragma: no cover
        raise EasyOcrNotInstalled(
            "EasyOCR n'est pas installé. Installe-le avec: "
            "`pip install easyocr` (ou via `pyproject.toml` extra `ocr`)."
        ) from e


@lru_cache(maxsize=8)
def _get_reader(languages: tuple[str, ...], gpu: bool):
    easyocr = _import_easyocr()
    # EasyOCR loads models the first time: caching here is critical.
    return easyocr.Reader(list(languages), gpu=gpu)


class EasyOcrAdapter:
    def __init__(self, settings: EasyOcrSettings) -> None:
        if not settings.languages:
            raise ValueError("EasyOCR languages cannot be empty")
        self._settings = settings

    def extract_text_from_image(self, file_path: str) -> str:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(file_path)

        reader = _get_reader(self._settings.languages, self._settings.gpu)

        # detail=0 -> only text strings; paragraph=True helps for natural text reconstruction.
        lines: list[str] = reader.readtext(str(path), detail=0, paragraph=True)
        # Join with newlines to preserve some structure.
        return "\n".join([ln for ln in lines if ln and ln.strip()])
