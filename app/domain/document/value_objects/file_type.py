"""File type value object/enum."""

from __future__ import annotations

from enum import StrEnum


class FileType(StrEnum):
    pdf = "pdf"
    image = "image"
    text = "text"
    other = "other"

    @staticmethod
    def from_filename(filename: str) -> "FileType":
        fn = (filename or "").lower()
        if fn.endswith(".pdf"):
            return FileType.pdf
        if fn.endswith((".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp")):
            return FileType.image
        if fn.endswith((".txt", ".md", ".csv", ".log", ".json")):
            return FileType.text
        return FileType.other
