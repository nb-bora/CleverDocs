from __future__ import annotations

from pathlib import Path


def main() -> None:
    root = Path(__file__).resolve().parents[1] / "app"
    scanned = 0
    changed = 0

    for p in root.rglob("*.py"):
        scanned += 1
        txt = p.read_text(encoding="utf-8")
        if "\\n" not in txt:
            continue
        new = txt.replace("\\n", "\n")
        if new != txt:
            p.write_text(new, encoding="utf-8")
            changed += 1

    print(f"fixed literal \\\\n sequences: scanned={scanned} changed={changed}")


if __name__ == "__main__":
    main()

