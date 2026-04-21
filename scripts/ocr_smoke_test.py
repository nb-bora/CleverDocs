from __future__ import annotations


def main() -> None:
    try:
        import easyocr  # noqa: F401
    except Exception as e:
        raise SystemExit(
            "EasyOCR n'est pas installé dans ton environnement.\n"
            "Installe-le avec: `pip install easyocr` (et idéalement `pip install pillow`).\n"
            f"Détail: {e}"
        )

    print("EASYOCR_OK")


if __name__ == "__main__":
    main()

