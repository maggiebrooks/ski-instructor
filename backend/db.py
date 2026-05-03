"""Thin DB connection helper for a future Postgres migration.

To migrate to Postgres: set DATABASE_URL=postgresql://... and update
backend/models.py and data/database.py to use get_connection().
"""

from __future__ import annotations

import os
import sqlite3


def get_connection():
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgresql") or url.startswith("postgres"):
        import psycopg2

        return psycopg2.connect(url)
    db_path = url.replace("sqlite:///", "") if url.startswith("sqlite:///") else None
    if not db_path:
        from backend.config import DATA_DIR

        db_path = str(DATA_DIR / "ski.db")
    return sqlite3.connect(db_path)
