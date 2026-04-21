"""OCR service port (interface)."""


class OcrService:
    def extract_text(self, *, file_path: str) -> str:
        raise NotImplementedError
