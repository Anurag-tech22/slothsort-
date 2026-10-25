"""Action log + memory in a local SQLite file (works fully offline).

Only metadata and embeddings are stored. File contents are never written to the DB.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .embed import cosine

FIELDS = ("src", "dst", "original_name", "clean_name", "category", "confidence",
          "status", "reason", "size", "mtime", "corrected", "embedding", "applied_at")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class BaseStore(ABC):
    @abstractmethod
    def add(self, **fields: Any) -> int: ...
    @abstractmethod
    def get(self, action_id: int) -> dict | None: ...
    @abstractmethod
    def list(self, status: str | None = None, limit: int = 200) -> list[dict]: ...
    @abstractmethod
    def update(self, action_id: int, **fields: Any) -> None: ...
    @abstractmethod
    def seen(self, src: str, mtime: float) -> bool: ...
    @abstractmethod
    def similar_to_vector(self, vec: list[float], k: int, exclude: int | None = None) -> list[dict]: ...
    @abstractmethod
    def keyword(self, q: str, k: int) -> list[dict]: ...
    @abstractmethod
    def stats(self) -> dict[str, int]: ...

    def similar(self, vec: list[float], k: int = 3, exclude: int | None = None) -> list[dict]:
        return self.similar_to_vector(vec, k, exclude)

    def search(self, q: str, vec: list[float], k: int = 10) -> list[dict]:
        """Hybrid search: keyword rank + vector rank fused with reciprocal rank fusion."""
        scores: dict[int, float] = {}
        rows: dict[int, dict] = {}
        for ranked in (self.keyword(q, k * 2), self.similar_to_vector(vec, k * 2, None, learned_only=False)):
            for rank, row in enumerate(ranked):
                rows[row["id"]] = row
                scores[row["id"]] = scores.get(row["id"], 0.0) + 1.0 / (60 + rank)
        order = sorted(scores, key=scores.get, reverse=True)[:k]
        return [rows[i] for i in order]


class SqliteStore(BaseStore):
    def __init__(self, path: Path | str):
        self.lock = threading.RLock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.execute("""CREATE TABLE IF NOT EXISTS actions(
                id INTEGER PRIMARY KEY AUTOINCREMENT, src TEXT NOT NULL, dst TEXT,
                original_name TEXT, clean_name TEXT, category TEXT, confidence REAL,
                status TEXT NOT NULL, reason TEXT, size INTEGER, mtime REAL,
                corrected INTEGER DEFAULT 0, embedding TEXT, created_at TEXT, applied_at TEXT)""")
            self.db.execute("CREATE INDEX IF NOT EXISTS idx_src ON actions(src, mtime)")
            self.db.commit()

    @staticmethod
    def _row(r: sqlite3.Row | None) -> dict | None:
        if r is None:
            return None
        d = dict(r)
        d["embedding"] = json.loads(d["embedding"]) if d.get("embedding") else []
        return d

    def add(self, **fields: Any) -> int:
        fields.setdefault("corrected", 0)
        if isinstance(fields.get("embedding"), list):
            fields["embedding"] = json.dumps(fields["embedding"])
        cols = [c for c in FIELDS if c in fields]
        with self.lock:
            cur = self.db.execute(
                f"INSERT INTO actions({','.join(cols)},created_at) VALUES({','.join('?' * len(cols))},?)",
                [fields[c] for c in cols] + [now_iso()])
            self.db.commit()
            return int(cur.lastrowid)

    def get(self, action_id: int) -> dict | None:
        with self.lock:
            return self._row(self.db.execute("SELECT * FROM actions WHERE id=?", (action_id,)).fetchone())

    def list(self, status: str | None = None, limit: int = 200) -> list[dict]:
        with self.lock:
            if status:
                rs = self.db.execute("SELECT * FROM actions WHERE status=? ORDER BY id DESC LIMIT ?", (status, limit))
            else:
                rs = self.db.execute("SELECT * FROM actions ORDER BY id DESC LIMIT ?", (limit,))
            return [self._row(r) for r in rs.fetchall()]

    def update(self, action_id: int, **fields: Any) -> None:
        cols = [c for c in FIELDS if c in fields]
        if not cols:
            return
        if isinstance(fields.get("embedding"), list):
            fields["embedding"] = json.dumps(fields["embedding"])
        with self.lock:
            self.db.execute(f"UPDATE actions SET {','.join(c + '=?' for c in cols)} WHERE id=?",
                            [fields[c] for c in cols] + [action_id])
            self.db.commit()

    def seen(self, src: str, mtime: float) -> bool:
        with self.lock:
            r = self.db.execute("SELECT 1 FROM actions WHERE src=? AND ABS(mtime-?)<0.001 LIMIT 1",
                                (src, mtime)).fetchone()
            return r is not None

    def similar_to_vector(self, vec, k, exclude=None, learned_only=True) -> list[dict]:
        where = "(status='applied' OR corrected=1)" if learned_only else "1=1"
        with self.lock:
            rows = [self._row(r) for r in self.db.execute(f"SELECT * FROM actions WHERE {where}").fetchall()]
        scored = []
        for r in rows:
            if exclude is not None and r["id"] == exclude or not r["embedding"]:
                continue
            r["score"] = cosine(vec, r["embedding"])
            scored.append(r)
        scored.sort(key=lambda r: r["score"], reverse=True)
        return scored[:k]

    def keyword(self, q: str, k: int) -> list[dict]:
        like = f"%{q.strip().lower()}%"
        with self.lock:
            rs = self.db.execute(
                "SELECT * FROM actions WHERE lower(original_name) LIKE ? OR lower(clean_name) LIKE ? "
                "OR lower(category) LIKE ? ORDER BY id DESC LIMIT ?", (like, like, like, k))
            return [self._row(r) for r in rs.fetchall()]

    def stats(self) -> dict[str, int]:
        with self.lock:
            rs = self.db.execute("SELECT status, COUNT(*) c FROM actions GROUP BY status").fetchall()
        return {r["status"]: r["c"] for r in rs}


def make_store(s: Settings) -> BaseStore:
    return SqliteStore(s.db_path)
