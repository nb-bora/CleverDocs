from __future__ import annotations

import os
import sqlite3


def main() -> None:
    db_path = "cleverdocs.db"
    if os.getenv("DATABASE_URL", "").startswith("sqlite:///./"):
        db_path = os.getenv("DATABASE_URL", "sqlite:///./cleverdocs.db").replace("sqlite:///./", "")

    conn = sqlite3.connect(db_path)
    try:
        cur = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table' AND name='document_search_fts'")
        row = cur.fetchone()
        print("fts_exists:", bool(row))
        if row:
            print("fts_sql:", row[1])
        cur = conn.execute("SELECT count(*) FROM document_search_fts")
        print("fts_count:", cur.fetchone()[0])
        cur = conn.execute("SELECT document_id, filename, length(content) FROM document_search_fts LIMIT 5")
        print("sample_rows:", cur.fetchall())

        q = "ingenieur"
        try:
            cur = conn.execute(
                "SELECT document_id, filename, bm25(document_search_fts) FROM document_search_fts "
                "WHERE document_search_fts MATCH ? LIMIT 5",
                (q,),
            )
            print("match_ingenieur:", cur.fetchall())
        except Exception as e:
            print("match_error:", repr(e))
    finally:
        conn.close()


if __name__ == "__main__":
    main()

