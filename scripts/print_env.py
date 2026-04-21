from __future__ import annotations

import os
import sys
from pathlib import Path


def main() -> None:
    print("cwd:", os.getcwd())
    print("sys.path[0]:", sys.path[0])
    print("repo_has_app_dir:", Path("app").is_dir())
    print("repo_has_readme:", Path("README.md").is_file())


if __name__ == "__main__":
    main()

