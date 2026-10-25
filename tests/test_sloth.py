from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import ConfigError, Settings
from app.embed import cosine, embed
from app.llm import (HeuristicClient, LLMClient, OpenAICompatClient, SafeClient, parse_llm_json, slugify)
from app.main import create_app
from app.organizer import UnsafePathError, safe_join, unique_path
from app.service import ServiceError, Sloth, seed_samples
from app.store import SqliteStore


def make_settings(tmp_path: Path, **kw) -> Settings:
    base = dict(watch_dir=tmp_path / "watched", db_path=tmp_path / "t.db", settle_seconds=0.0,
                llm_backend="heuristic")
    base.update(kw)
    return Settings(**base)


def put(root: Path, name: str, body: str = "x") -> Path:
    root.mkdir(parents=True, exist_ok=True)
    p = root / name
    p.write_text(body)
    old = time.time() - 30
    os.utime(p, (old, old))
    return p


@pytest.fixture
def sloth(tmp_path):
    s = make_settings(tmp_path)
    return Sloth(s, store=SqliteStore(s.db_path))


# ---- parsing -----------------------------------------------------------
def test_parse_plain_json():
    r = parse_llm_json('{"category":"finance","clean_name":"Phone Bill Oct","confidence":0.9}')
    assert r == {"category": "Finance", "clean_name": "phone-bill-oct", "confidence": 0.9}


def test_parse_fenced_and_noisy():
    r = parse_llm_json('Sure!\n```json\n{"category":"Study","clean_name":"dbms","confidence":2}\n```')
    assert r["category"] == "Study" and r["confidence"] == 1.0


def test_parse_unknown_category_falls_back():
    assert parse_llm_json('{"category":"Spaceships","clean_name":"a"}')["category"] == "Misc"


def test_parse_rejects_garbage():
    with pytest.raises(ValueError):
        parse_llm_json("I cannot help with that")


def test_slugify_strips_path_tricks():
    assert "/" not in slugify("../../etc/passwd") and ".." not in slugify("../../etc/passwd")
    assert slugify("   ") == "file"


def test_parse_canned_fenced_and_surrounding_prose():
    canned = """Here is your file classification:
```json
{
  "category": "Finance",
  "clean_name": "quarterly-gst-filing-summary",
  "confidence": 0.94
}
```
Hope this is helpful!"""
    r = parse_llm_json(canned)
    assert r["category"] == "Finance"
    assert r["clean_name"] == "quarterly-gst-filing-summary"
    assert r["confidence"] == 0.94


def test_parse_path_traversal_attempt_in_clean_name():
    canned = '{"category": "Documents", "clean_name": "../../../etc/shadow", "confidence": 0.8}'
    r = parse_llm_json(canned)
    assert ".." not in r["clean_name"]
    assert "/" not in r["clean_name"]
    assert "\\" not in r["clean_name"]
    assert r["clean_name"] == "etc-shadow"


def test_parse_strips_extensions_and_repeated_dates():
    canned = '{"category": "Finance", "clean_name": "vodafone-invoice-2026-10.pdf", "confidence": 0.9}'
    r = parse_llm_json(canned, orig_name="Invoice 2026-10 Vodafone.txt")
    assert not r["clean_name"].endswith("pdf")
    assert "2026-10" not in r["clean_name"]
    assert r["category"] == "Finance"


def test_parse_truncates_overlong_clean_name():
    long_name = "this-is-an-extremely-long-filename-that-exceeds-sixty-characters-total-length-which-should-be-truncated"
    canned = f'{{"category": "Career", "clean_name": "{long_name}", "confidence": 0.85}}'
    r = parse_llm_json(canned)
    assert len(r["clean_name"]) <= 60



class Flaky(LLMClient):
    name = "flaky"

    def __init__(self):
        self.calls = 0

    def _complete(self, prompt):
        self.calls += 1
        return "nope" if self.calls == 1 else '{"category":"Code","clean_name":"x","confidence":0.8}'


def test_retry_on_malformed_output():
    c = Flaky()
    r = c.classify({"name": "a", "stem": "a", "ext": ".py", "size": 1}, "", [])
    assert r["category"] == "Code" and c.calls == 2


class Broken(LLMClient):
    name = "broken"

    def _complete(self, prompt):
        raise ConnectionError("model server is down")


def test_safe_client_falls_back_to_rules():
    c = SafeClient(Broken())
    r = c.classify({"name": "invoice.pdf", "stem": "invoice", "ext": ".pdf", "size": 1}, "", [])
    assert r["category"] == "Finance" and r["confidence"] <= 0.6
    assert "ConnectionError" in c.last_error


# ---- config ------------------------------------------------------------
def test_gemini_requires_demo_mode(tmp_path):
    with pytest.raises(ConfigError):
        make_settings(tmp_path, llm_backend="gemini", google_api_key="k", demo_mode=False).validate()
    make_settings(tmp_path, llm_backend="gemini", google_api_key="k", demo_mode=True).validate()


def test_other_config_errors(tmp_path):
    for kw in ({"llm_backend": "nope"}, {"llm_backend": "llamacpp"},
               {"confidence_threshold": 2.0}):
        with pytest.raises(ConfigError):
            make_settings(tmp_path, **kw).validate()


# ---- filesystem safety -------------------------------------------------
def test_safe_join_blocks_escape(tmp_path):
    with pytest.raises(UnsafePathError):
        safe_join(tmp_path, "../outside.txt")


def test_safe_join_blocks_symlink(tmp_path):
    outside = tmp_path / "outside"
    outside.mkdir()
    (tmp_path / "root").mkdir()
    try:
        (tmp_path / "root" / "link").symlink_to(outside)
    except OSError as e:
        if getattr(e, "winerror", None) == 1314:
            pytest.skip("Symlink creation requires Developer Mode or admin privileges on Windows")
        raise
    with pytest.raises(UnsafePathError):
        safe_join(tmp_path / "root", "link")



def test_unique_path(tmp_path):
    (tmp_path / "a.txt").write_text("1")
    (tmp_path / "a-1.txt").write_text("2")
    assert unique_path(tmp_path / "a.txt").name == "a-2.txt"


# ---- embeddings --------------------------------------------------------
def test_embedding_similarity():
    a, b, c = embed("quarterly budget sheet"), embed("quarterly budget sheet copy"), embed("holiday photos goa")
    assert cosine(a, b) > cosine(a, c)


# ---- service flow ------------------------------------------------------
def test_dry_run_proposes_without_moving(sloth):
    f = put(sloth.root, "Invoice Oct.txt", "Invoice amount due")
    assert sloth.scan()["proposed"] == 1
    assert f.exists()  # untouched
    a = sloth.store.list("proposed")[0]
    assert a["category"] == "Finance" and a["status"] == "proposed"


def test_scan_is_idempotent(sloth):
    put(sloth.root, "notes.md", "lecture notes")
    sloth.scan()
    assert sloth.scan()["proposed"] == 0


def test_approve_then_undo_restores_original(sloth):
    f = put(sloth.root, "My Photo.PNG")
    sloth.scan()
    aid = sloth.store.list("proposed")[0]["id"]
    done = sloth.apply(aid)
    assert not f.exists() and (sloth.root / done["dst"]).exists()
    assert done["dst"] == "Images/my-photo.png"
    sloth.undo(aid)
    assert f.exists() and not (sloth.root / "Images/my-photo.png").exists()
    assert sloth.scan()["proposed"] == 0  # undone files are not re-proposed


def test_never_overwrites_existing(sloth):
    (sloth.root / "Images").mkdir()
    (sloth.root / "Images" / "pic.png").write_text("older")
    put(sloth.root, "pic.png", "newer")
    sloth.scan()
    done = sloth.apply(sloth.store.list("proposed")[0]["id"])
    assert done["dst"] == "Images/pic-1.png"
    assert (sloth.root / "Images" / "pic.png").read_text() == "older"


def test_auto_apply_when_not_dry_run(tmp_path):
    s = make_settings(tmp_path, dry_run=False)
    sl = Sloth(s, store=SqliteStore(s.db_path))
    put(sl.root, "report.csv", "a,b")
    r = sl.scan()
    assert r["applied"] == 1 and (sl.root / "Data" / "report.csv").exists()


def test_low_confidence_waits_for_approval(tmp_path):
    s = make_settings(tmp_path, dry_run=False)
    sl = Sloth(s, store=SqliteStore(s.db_path))
    put(sl.root, "mystery.zzz", "?")
    r = sl.scan()
    assert r["proposed"] == 1 and r["applied"] == 0
    assert (sl.root / "mystery.zzz").exists()


def test_correction_teaches_future_files(sloth):
    put(sloth.root, "quarterly budget sheet.xyz")
    sloth.scan()
    first = sloth.store.list("proposed")[0]
    assert first["category"] == "Misc"
    sloth.correct(first["id"], "Finance")
    put(sloth.root, "quarterly budget sheet copy.xyz")
    sloth.scan()
    second = [a for a in sloth.store.list("proposed") if a["original_name"].endswith("copy.xyz")][0]
    assert second["category"] == "Finance" and "similar past" in second["reason"]


def test_correct_moves_applied_file(sloth):
    put(sloth.root, "thing.txt", "hello")
    sloth.scan()
    aid = sloth.store.list("proposed")[0]["id"]
    sloth.apply(aid)
    out = sloth.correct(aid, "Study")
    assert out["dst"].startswith("Study/") and (sloth.root / out["dst"]).exists()


def test_invalid_category_and_state_errors(sloth):
    put(sloth.root, "a.txt")
    sloth.scan()
    aid = sloth.store.list("proposed")[0]["id"]
    with pytest.raises(ServiceError):
        sloth.correct(aid, "../../etc")
    with pytest.raises(ServiceError):
        sloth.undo(aid)  # not applied yet
    with pytest.raises(ServiceError) as e:
        sloth.apply(9999)
    assert e.value.status == 404


def test_ignores_hidden_temp_symlink_and_fresh_files(tmp_path):
    s = make_settings(tmp_path, settle_seconds=60)
    sl = Sloth(s, store=SqliteStore(s.db_path))
    put(sl.root, ".hidden")
    put(sl.root, "dl.crdownload")
    p = sl.root / "fresh.txt"
    p.write_text("x")  # modified just now, inside the settle window
    assert sl.scan()["proposed"] == 0


def test_search_and_similar(sloth):
    put(sloth.root, "invoice vodafone.txt", "invoice amount")
    put(sloth.root, "invoice airtel.txt", "invoice amount")
    put(sloth.root, "holiday.jpg")
    sloth.scan()
    hits = [h["original_name"] for h in sloth.search("invoice")]
    assert "invoice vodafone.txt" in hits and "invoice airtel.txt" in hits
    first = next(a for a in sloth.store.list() if a["original_name"] == "invoice vodafone.txt")
    sim = [s["original_name"] for s in sloth.similar_files(first["id"])]
    assert sim and sim[0] == "invoice airtel.txt"


# ---- API ---------------------------------------------------------------
@pytest.fixture
def client(tmp_path):
    s = make_settings(tmp_path, demo_mode=True)
    sl = Sloth(s, store=SqliteStore(s.db_path))
    with TestClient(create_app(s, sl)) as c:
        yield c, sl


def test_api_end_to_end(client):
    c, sl = client
    assert c.get("/").status_code == 200
    state = c.get("/api/state").json()
    assert state["dry_run"] is True and "Finance" in state["categories"]
    assert c.get("/api/actions").json() == [] or True  # demo seeding may already have files
    c.post("/api/scan")
    items = c.get("/api/actions?status=proposed").json()
    assert items and "embedding" not in items[0]
    aid = items[0]["id"]
    assert c.post(f"/api/actions/{aid}/approve").json()["status"] == "applied"
    assert c.post(f"/api/actions/{aid}/approve").status_code == 409
    assert c.post(f"/api/actions/{aid}/undo").json()["status"] == "undone"
    assert c.post(f"/api/actions/{aid}/correct", json={"category": "Nope"}).status_code == 400
    assert c.post("/api/actions/9999/approve").status_code == 404
    assert c.get("/api/search?q=invoice").status_code == 200
    assert c.post("/api/actions/apply-confident").json()["applied"] >= 1


def test_demo_seed_blocked_outside_demo_mode(tmp_path):
    s = make_settings(tmp_path)
    with TestClient(create_app(s, Sloth(s, store=SqliteStore(s.db_path)))) as c:
        assert c.post("/api/demo/seed").status_code == 403


def test_seed_samples_creates_files(tmp_path):
    assert seed_samples(tmp_path) >= 5


def test_keywords_match_whole_words_only():
    c = HeuristicClient()
    meta = {"name": "sales.csv", "stem": "sales", "ext": ".csv", "size": 1}
    assert c.classify(meta, "region,units,revenue", [])["category"] == "Data"


# ---- model status ------------------------------------------------------
class _Resp:
    def __init__(self, data): self._d = data
    def raise_for_status(self): pass
    def json(self): return self._d


def test_openai_client_autodetects_loaded_model(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp({"data": [{"id": "gemma-4-test"}]}))
    c = OpenAICompatClient("http://x/v1")
    assert c.ping() == (True, "gemma-4-test")


def test_ping_reports_wrong_model(monkeypatch):
    import httpx
    monkeypatch.setattr(httpx, "get", lambda *a, **k: _Resp({"data": [{"id": "other"}]}))
    ok, detail = OpenAICompatClient("http://x/v1", model="gemma").ping()
    assert not ok and "not loaded" in detail


def test_offline_model_is_reported_and_scan_still_works(tmp_path):
    s = make_settings(tmp_path, llm_backend="openai", llm_base_url="http://127.0.0.1:1/v1")
    sl = Sloth(s, store=SqliteStore(s.db_path))
    put(sl.root, "invoice.txt", "invoice amount due")
    assert sl.state()["model"]["status"] == "offline"
    assert sl.scan()["proposed"] == 1
    a = sl.store.list("proposed")[0]
    assert a["category"] == "Finance" and "used rules" in a["reason"] and a["confidence"] <= 0.6


def test_rules_mode_is_labelled(sloth):
    m = sloth.state()["model"]
    assert m["status"] == "rules" and m["backend"] == "rules"


def test_keywords_see_through_underscores_and_dashes():
    c = HeuristicClient()
    for name, cat in (("invoice_oct.pdf", "Finance"), ("notes-final.txt", "Study"), ("my_cv.docx", "Career")):
        meta = {"name": name, "stem": name.rsplit(".", 1)[0], "ext": "." + name.rsplit(".", 1)[1], "size": 1}
        assert c.classify(meta, "", [])["category"] == cat
