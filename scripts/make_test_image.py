from __future__ import annotations

from pathlib import Path


def main() -> None:
    try:
        from PIL import Image, ImageDraw  # type: ignore
    except Exception:
        raise SystemExit(
            "Pillow n'est pas installé. Installe-le avec `pip install pillow` "
            "ou utilise directement une image existante."
        )

    img = Image.new("RGB", (800, 240), (255, 255, 255))
    d = ImageDraw.Draw(img)
    d.text((20, 80), "CleverDocs OCR TEST 123", fill=(0, 0, 0))

    out_dir = Path("storage")
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / "ocr_test.png"
    img.save(out)
    print(str(out))


if __name__ == "__main__":
    main()

