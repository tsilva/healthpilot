"""Transactional daily coverage; successful empty days are durable cache entries."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path
from typing import Any

from healthpilot.google_health_auth import GoogleHealthError


class CoverageCache:
    def __init__(self, directory: Path, binding: str):
        path = directory / "measurements.sqlite3"
        if path.is_symlink():
            raise GoogleHealthError("unreadable", "Google Health cache must not be a symbolic link.")
        fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        os.fchmod(fd, 0o600)
        os.close(fd)
        self.db = sqlite3.connect(path)
        self.db.execute("CREATE TABLE IF NOT EXISTS identity (binding TEXT NOT NULL)")
        row = self.db.execute("SELECT binding FROM identity").fetchone()
        if row and row[0] != binding:
            self.db.close()
            raise GoogleHealthError("unavailable", "Google Health cache belongs to a different profile or account.")
        if not row:
            self.db.execute("INSERT INTO identity VALUES (?)", (binding,))
        self.db.execute("""CREATE TABLE IF NOT EXISTS days (
            metric TEXT NOT NULL, day TEXT NOT NULL, fetched_at TEXT NOT NULL,
            records TEXT NOT NULL, error TEXT NOT NULL DEFAULT '',
            PRIMARY KEY(metric, day))""")
        self.db.commit()

    def close(self) -> None:
        self.db.close()

    def days(self, metric: str) -> dict[str, dict[str, Any]]:
        return {day: {"fetched_at": fetched, "records": json.loads(records), "error": error}
                for day, fetched, records, error in self.db.execute(
                    "SELECT day, fetched_at, records, error FROM days WHERE metric = ?", (metric,))}

    def save(self, metric: str, days: dict[str, list[dict[str, Any]]], fetched_at: str) -> None:
        with self.db:
            self.db.executemany("INSERT OR REPLACE INTO days VALUES (?, ?, ?, ?, '')",
                                [(metric, day, fetched_at, json.dumps(rows)) for day, rows in days.items()])

    def fail(self, metric: str, days: list[str], error: str) -> None:
        # Keep previously complete measurements and mark the failed refresh explicitly.
        with self.db:
            self.db.executemany("""INSERT INTO days VALUES (?, ?, '', '[]', ?)
                ON CONFLICT(metric, day) DO UPDATE SET error = excluded.error""",
                                [(metric, day, error) for day in days])
