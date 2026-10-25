from __future__ import annotations

import threading
import time
from pathlib import Path

from .config import Settings
from .embed import embed
from .llm import CATEGORIES, LLMClient, build_client, slugify
from .organizer import apply_move, plan_destination, undo_move
from .store import BaseStore, make_store, now_iso

TEXT_EXT = {".txt", ".md", ".csv", ".json", ".py", ".js", ".ts", ".html", ".css", ".log",
            ".tsv", ".sql", ".yaml", ".yml", ".rtf", ".sh"}
TEMP_SUFFIX = {".crdownload", ".part", ".tmp", ".download", ".swp"}
MINUTES_SAVED_PER_FILE = 0.5  # rough estimate, shown as an estimate in the UI


class ServiceError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def extract_snippet(path: Path, limit: int) -> str:
    ext = path.suffix.lower()
    try:
        if ext in TEXT_EXT:
            with open(path, "rb") as f:
                return f.read(limit).decode("utf-8", errors="ignore")
        if ext == ".pdf":
            try:
                from pypdf import PdfReader  # optional
                text = PdfReader(str(path)).pages[0].extract_text() or ""
                return text[:limit]
            except Exception:
                return ""
    except OSError:
        return ""
    return ""


def public(action: dict | None) -> dict | None:
    if action is None:
        return None
    return {k: v for k, v in action.items() if k not in {"embedding"}}


class Sloth:
    def __init__(self, settings: Settings, store: BaseStore | None = None, client: LLMClient | None = None):
        self.s = settings
        self.s.watch_dir.mkdir(parents=True, exist_ok=True)
        self.root = self.s.watch_dir.resolve()
        self.store = store or make_store(settings)
        self.client = client or build_client(settings)
        self.lock = threading.RLock()
        self.dry_run = settings.dry_run
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._ping_cache: tuple[float, tuple[bool, str]] = (0.0, (True, ""))

    def model_status(self) -> dict:
        """online | degraded | offline | rules, cached for 10s so the UI can poll."""
        if self.client.name == "rules":
            return {"backend": "rules", "status": "rules", "detail": "No AI model: simple extension and keyword rules."}
        at, cached = self._ping_cache
        if time.time() - at > 10:
            cached = self.client.ping()
            self._ping_cache = (time.time(), cached)
        ok, detail = cached
        err = getattr(self.client, "last_error", None)
        status = "offline" if not ok else ("degraded" if err else "online")
        return {"backend": self.client.name, "status": status, "detail": err or detail}

    # ---- scanning -------------------------------------------------------
    def scan(self) -> dict[str, int]:
        result = {"proposed": 0, "applied": 0, "ignored": 0}
        with self.lock:
            for entry in sorted(self.root.iterdir()):
                if entry.is_symlink() or not entry.is_file() or entry.name.startswith("."):
                    continue
                if entry.suffix.lower() in TEMP_SUFFIX:
                    continue
                st = entry.stat()
                if time.time() - st.st_mtime < self.s.settle_seconds:
                    result["ignored"] += 1  # probably still being written
                    continue
                if self.store.seen(entry.name, st.st_mtime):
                    continue
                action_id = self._propose(entry, st)
                result["proposed"] += 1
                action = self.store.get(action_id)
                if (not self.dry_run) and action["confidence"] >= self.s.confidence_threshold:
                    self.apply(action_id)
                    result["applied"] += 1
        return result

    def _propose(self, entry: Path, st) -> int:
        snippet = extract_snippet(entry, self.s.snippet_bytes)
        meta = {"name": entry.name, "stem": entry.stem, "ext": entry.suffix.lower(), "size": st.st_size}
        vec = embed(f"{entry.stem} {snippet}")
        examples = [
            {"original_name": r["original_name"], "category": r["category"],
             "clean_name": r["clean_name"], "score": r["score"]}
            for r in self.store.similar(vec, 3)
        ]
        c = self.client.classify(meta, snippet, examples)
        reason = f"{self.client.name}"
        if examples:
            reason += f" + {len(examples)} similar past file(s)"
        err = getattr(self.client, "last_error", None)
        if err:
            reason += f" (model unavailable, used rules: {err[:80]})"
        return self.store.add(
            src=entry.name, dst=None, original_name=entry.name, clean_name=c["clean_name"],
            category=c["category"], confidence=c["confidence"], status="proposed", reason=reason,
            size=st.st_size, mtime=st.st_mtime, embedding=vec)

    # ---- actions --------------------------------------------------------
    def _require(self, action_id: int, *statuses: str) -> dict:
        a = self.store.get(action_id)
        if a is None:
            raise ServiceError("Action not found.", 404)
        if a["status"] not in statuses:
            raise ServiceError(f"Action is '{a['status']}', expected {' or '.join(statuses)}.", 409)
        return a

    def apply(self, action_id: int) -> dict:
        with self.lock:
            a = self._require(action_id, "proposed")
            ext = Path(a["original_name"]).suffix
            try:
                dst = apply_move(self.root, a["src"], plan_destination(a["category"], a["clean_name"], ext))
            except FileNotFoundError:
                self.store.update(action_id, status="skipped", reason="file no longer exists")
                raise ServiceError("File no longer exists.", 410)
            self.store.update(action_id, status="applied", dst=dst, applied_at=now_iso())
            return public(self.store.get(action_id))

    def undo(self, action_id: int) -> dict:
        with self.lock:
            a = self._require(action_id, "applied")
            try:
                undo_move(self.root, a["src"], a["dst"])
            except FileNotFoundError:
                raise ServiceError("The moved file is gone, so it can't be restored.", 410)
            self.store.update(action_id, status="undone")
            return public(self.store.get(action_id))

    def skip(self, action_id: int) -> dict:
        with self.lock:
            self._require(action_id, "proposed")
            self.store.update(action_id, status="skipped")
            return public(self.store.get(action_id))

    def correct(self, action_id: int, category: str) -> dict:
        if category not in CATEGORIES:
            raise ServiceError(f"Category must be one of: {', '.join(CATEGORIES)}.")
        with self.lock:
            a = self._require(action_id, "proposed", "applied")
            fields = {"category": category, "corrected": 1, "confidence": 1.0}
            if a["status"] == "applied":
                ext = Path(a["original_name"]).suffix
                new_dst = plan_destination(category, Path(a["dst"]).stem, ext)
                fields["dst"] = apply_move(self.root, a["dst"], new_dst)
            self.store.update(action_id, **fields)
            return public(self.store.get(action_id))

    def apply_confident(self) -> int:
        n = 0
        with self.lock:
            for a in reversed(self.store.list("proposed")):
                if a["confidence"] >= self.s.confidence_threshold:
                    try:
                        self.apply(a["id"])
                        n += 1
                    except ServiceError:
                        pass
        return n

    # ---- reads ----------------------------------------------------------
    def state(self) -> dict:
        stats = self.store.stats()
        applied = stats.get("applied", 0)
        return {
            "watch_dir": str(self.root),
            "llm_backend": self.client.name,
            "model": self.model_status(),
            "dry_run": self.dry_run,
            "demo_mode": self.s.demo_mode,
            "auto_watch": self._thread is not None and self._thread.is_alive(),
            "confidence_threshold": self.s.confidence_threshold,
            "stats": stats,
            "minutes_saved_estimate": round(applied * MINUTES_SAVED_PER_FILE, 1),
            "categories": CATEGORIES,
        }

    def similar_files(self, action_id: int, k: int = 5) -> list[dict]:
        a = self.store.get(action_id)
        if a is None:
            raise ServiceError("Action not found.", 404)
        rows = self.store.similar_to_vector(a["embedding"], k, exclude=action_id, learned_only=False)
        return [public(r) | {"score": round(r["score"], 3)} for r in rows if r["score"] > 0.15]

    def search(self, q: str, k: int = 10) -> list[dict]:
        return [public(r) for r in self.store.search(q, embed(q), k)]

    # ---- background watching -------------------------------------------
    def start_watching(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()

        def loop() -> None:
            while not self._stop.wait(self.s.poll_seconds):
                try:
                    self.scan()
                except Exception:  # keep the watcher alive no matter what
                    pass

        self._thread = threading.Thread(target=loop, name="sloth-watch", daemon=True)
        self._thread.start()

    def stop_watching(self) -> None:
        self._stop.set()


SAMPLES = {
    "Invoice 2026-10 Vodafone.txt": "Invoice #4431\nAmount due: INR 899\nPayment due 05 Nov 2026\nBank transfer / UPI accepted.",
    "IMG_2041 (final).JPG": "",
    "DBMS lecture notes unit 3.md": "# DBMS Unit 3\nNormalization, 1NF 2NF 3NF, BCNF.\nExam important questions.",
    "Resume_Royeb_v7 FINAL.txt": "Resume. Computer Engineering student. Internship experience. Portfolio links.",
    "scan0042.txt": "GST registration certificate. Quarterly returns filed. Ledger balance carried forward to next quarter.",
    "sales_export (1).csv": "region,units,revenue\nWest,120,5400\nEast,98,4100\n",
    "setup_v2.exe": "",
    "project backup oct.zip": "",
    "random thoughts.txt": "grocery list: eggs, rice, tea. call plumber.",
    "main_FINAL_v3.py": "def main():\n    print('hello')\n",
}


def seed_samples(root: Path) -> int:
    n = 0
    for name, body in SAMPLES.items():
        p = root / name
        if not p.exists():
            p.write_text(body)
            old = time.time() - 60
            import os
            os.utime(p, (old, old))
            n += 1
    return n
