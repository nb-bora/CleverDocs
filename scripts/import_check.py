from __future__ import annotations

import sys
from pathlib import Path


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(repo_root))

    import app  # noqa: F401
    from app.interfaces.api.main import app as fastapi_app  # noqa: F401

    print("OK")


if __name__ == "__main__":
    main()

