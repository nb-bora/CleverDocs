"""OCR service implementation.

We keep the domain clean by implementing the `OcrService` port in infrastructure.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tempfile

from app.domain.processing.services.ocr_service import OcrService
from app.domain.processing.services.text_cleaner import TextCleaner
from app.infrastructure.ocr.easyocr_adapter import EasyOcrAdapter, EasyOcrSettings


class PdfOcrNotInstalled(RuntimeError):
    pass


@dataclass(frozen=True)
class OcrConfig:
    languages: tuple[str, ...] = ("fr",)
    gpu: bool = False
    pdf_max_pages: int = 20
    pdf_zoom: float = 2.0  # 2.0 ~ 144 DPI equivalent (good OCR baseline)


class BasicTextCleaner(TextCleaner):
    def clean(self, raw_text: str) -> str:
        # MVP: normalize whitespace while preserving newlines.
        lines = [ln.strip() for ln in raw_text.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
        # Collapse repeated empty lines
        cleaned_lines: list[str] = []
        empty_run = 0
        for ln in lines:
            if ln == "":
                empty_run += 1
                if empty_run <= 1:
                    cleaned_lines.append("")
            else:
                empty_run = 0
                cleaned_lines.append(ln)
        return "\n".join(cleaned_lines).strip()


class OcrServiceImpl(OcrService):
    def __init__(self, config: OcrConfig, cleaner: TextCleaner | None = None) -> None:
        self._config = config
        self._cleaner = cleaner or BasicTextCleaner()
        self._easy = EasyOcrAdapter(EasyOcrSettings(languages=config.languages, gpu=config.gpu))

    def extract_text(self, *, file_path: str) -> str:
        path = Path(file_path)
        suffix = path.suffix.lower()
        image_like = suffix in {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}
        if image_like:
            raw = self._easy.extract_text_from_image(str(path))
            return self._cleaner.clean(raw)

        if suffix == ".pdf":
            return self._extract_text_from_pdf(str(path))

        raise ValueError(f"Unsupported OCR file type: {suffix}")

    def _extract_text_from_pdf(self, file_path: str) -> str:
        try:
            import fitz  # PyMuPDF  # type: ignore
        except Exception as e:  # pragma: no cover
            raise PdfOcrNotInstalled(
                "PyMuPDF n'est pas installé (nécessaire pour OCR PDF). "
                "Installe-le avec: `pip install pymupdf` (ou `pip install -e \".[ocr]\"`)."
            ) from e

        doc = fitz.open(file_path)
        try:
            page_count = doc.page_count
            max_pages = max(1, int(self._config.pdf_max_pages))
            pages_to_process = min(page_count, max_pages)

            extracted_pages: list[str] = []
            zoom = float(self._config.pdf_zoom)
            mat = fitz.Matrix(zoom, zoom)

            with tempfile.TemporaryDirectory(prefix="cleverdocs_pdf_ocr_") as tmpdir:
                for i in range(pages_to_process):
                    page = doc.load_page(i)
                    pix = page.get_pixmap(matrix=mat, alpha=False)
                    img_path = Path(tmpdir) / f"page_{i+1:04d}.png"
                    pix.save(str(img_path))

                    page_text = self._easy.extract_text_from_image(str(img_path))
                    page_text = self._cleaner.clean(page_text)
                    if page_text:
                        extracted_pages.append(page_text)

            # Separate pages to preserve document structure.
            return "\n\n--- PAGE BREAK ---\n\n".join(extracted_pages).strip()
        finally:
            doc.close()
