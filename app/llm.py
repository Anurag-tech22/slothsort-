"""Pluggable LLM layer. Open weights first; the heuristic backend needs no model."""
from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from typing import Any

import httpx

from .config import ConfigError, Settings

CATEGORIES = [
    "Documents", "Finance", "Study", "Career", "Images", "Media", "Code",
    "Data", "Archives", "Installers", "Misc",
]

EXT_MAP = {
    "Documents": {".doc", ".docx", ".odt", ".rtf", ".txt", ".md", ".pdf", ".pptx", ".ppt"},
    "Images": {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".heic", ".bmp"},
    "Media": {".mp3", ".wav", ".flac", ".mp4", ".mkv", ".mov", ".avi", ".m4a"},
    "Code": {".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".c", ".cpp", ".go", ".rs", ".html", ".css", ".sh", ".ipynb"},
    "Data": {".csv", ".json", ".xlsx", ".xls", ".tsv", ".parquet", ".sql", ".db"},
    "Archives": {".zip", ".tar", ".gz", ".7z", ".rar", ".bz2"},
    "Installers": {".exe", ".msi", ".dmg", ".apk", ".deb", ".pkg"},
}

KEYWORDS = {
    "Finance": ["invoice", "receipt", "bill", "payment", "statement", "tax", "salary", "bank", "upi"],
    "Study": ["assignment", "lecture", "notes", "syllabus", "exam", "semester", "lab", "unit", "chapter", "paper"],
    "Career": ["resume", "cv", "cover letter", "offer letter", "internship", "portfolio", "interview"],
}

PROMPT = """You organise files. Choose ONE category from: {cats}.
Propose a short, descriptive clean_name (2 to 6 words, lowercase hyphenated) based on what the file is about using the text snippet when available.

Rules for clean_name:
- 2 to 6 words, lowercase letters, numbers, and single hyphens only.
- Never include file extensions (such as .pdf, .txt, .md, .docx).
- Never repeat dates already present in the original filename.
- Never exceed 60 characters in length.

Few-shot examples:
- File: scan0042.pdf | Snippet: "Invoice #4431 Vodafone Amount due: INR 899 Payment due 05 Nov"
  {{"category": "Finance", "clean_name": "vodafone-monthly-invoice", "confidence": 0.95}}
- File: unit3_notes.txt | Snippet: "DBMS Normalization 1NF 2NF 3NF BCNF practice questions"
  {{"category": "Study", "clean_name": "dbms-normalization-lecture-notes", "confidence": 0.95}}
- File: royeb_cv.docx | Snippet: "Software engineering graduate. Python, React. Past internships and projects."
  {{"category": "Career", "clean_name": "software-engineering-resume", "confidence": 0.95}}

Reply with ONLY a JSON object: {{"category": "...", "clean_name": "...", "confidence": 0.0-1.0}}

File name: {name}
Extension: {ext}
Size bytes: {size}
Text snippet (may be empty):
{snippet}
{examples}"""


def slugify(stem: str, max_len: int = 60, orig_name: str = "") -> str:
    stem = re.sub(r"\.[a-zA-Z0-9]{1,5}$", "", stem.strip())
    if orig_name:
        dates = re.findall(r"\b(19\d\d|20\d\d)(?:[-_.]\d{1,2}(?:[-_.]\d{1,2})?)?\b", orig_name)
        for d in dates:
            stem = re.sub(rf"\b{re.escape(d)}\b", "", stem, flags=re.IGNORECASE)
    s = re.sub(r"[^a-z0-9]+", "-", stem.lower()).strip("-")
    s = re.sub(r"-{2,}", "-", s)
    words = [w for w in s.split("-") if w]
    if len(words) > 6:
        s = "-".join(words[:6])
    return (s[:max_len].strip("-")) or "file"


def parse_llm_json(text: str, orig_name: str = "") -> dict[str, Any]:
    """Extract and validate the classification JSON. Raises ValueError if unusable."""
    cleaned = re.sub(r"```(?:json)?", "", text)
    match = re.search(r"\{.*?\}", cleaned, re.S)
    if not match:
        raise ValueError("no JSON object in model output")
    data = json.loads(match.group(0))
    if not isinstance(data, dict):
        raise ValueError("model output is not a JSON object")
    category = str(data.get("category", "")).strip()
    by_lower = {c.lower(): c for c in CATEGORIES}
    category = by_lower.get(category.lower(), "Misc")
    try:
        confidence = float(data.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5
    raw_clean = str(data.get("clean_name", "")).strip()
    return {
        "category": category,
        "clean_name": slugify(raw_clean, max_len=60, orig_name=orig_name),
        "confidence": max(0.0, min(1.0, confidence)),
    }


def build_prompt(meta: dict, snippet: str, examples: list[dict]) -> str:
    ex = ""
    if examples:
        lines = [f'- "{e["original_name"]}" -> {e["category"]} ({e["clean_name"]})' for e in examples]
        ex = "\nSimilar files this user already sorted (follow these habits):\n" + "\n".join(lines)
    return PROMPT.format(
        cats=", ".join(CATEGORIES), name=meta["name"], ext=meta["ext"],
        size=meta["size"], snippet=snippet[:1024] or "(none)", examples=ex,
    )


class LLMClient(ABC):
    name = "base"

    def ping(self) -> tuple[bool, str]:
        """Cheap reachability check shown in the dashboard."""
        return True, "ready"

    @abstractmethod
    def _complete(self, prompt: str) -> str: ...

    def classify(self, meta: dict, snippet: str, examples: list[dict]) -> dict[str, Any]:
        prompt = build_prompt(meta, snippet, examples)
        for _ in range(2):  # one retry on malformed output
            try:
                return parse_llm_json(self._complete(prompt), orig_name=meta.get("name", ""))
            except (ValueError, json.JSONDecodeError):
                continue
        raise ValueError("model returned malformed output twice")


class HeuristicClient(LLMClient):
    """No AI. Extension and keyword rules; the emergency fallback, clearly labelled in the UI."""
    name = "rules"

    def _complete(self, prompt: str) -> str:  # pragma: no cover - unused
        raise NotImplementedError

    def classify(self, meta: dict, snippet: str, examples: list[dict]) -> dict[str, Any]:
        haystack = re.sub(r"[^a-z0-9]+", " ", f'{meta["name"]} {snippet}'.lower())  # "invoice_oct" -> words
        stem = slugify(meta["stem"])
        for cat, words in KEYWORDS.items():
            if any(re.search(rf"\b{re.escape(w)}\b", haystack) for w in words):
                return {"category": cat, "clean_name": stem, "confidence": 0.75}
        for cat, exts in EXT_MAP.items():
            if meta["ext"] in exts:
                return {"category": cat, "clean_name": stem, "confidence": 0.7}
        if examples and examples[0].get("score", 0) > 0.6:
            return {"category": examples[0]["category"], "clean_name": stem, "confidence": 0.65}
        return {"category": "Misc", "clean_name": stem, "confidence": 0.3}


class OpenAICompatClient(LLMClient):
    """LM Studio, llama.cpp server, vLLM, or anything OpenAI-compatible."""
    name = "openai"

    def __init__(self, base_url: str, model: str = "", timeout: float = 60.0):
        self.base = base_url.rstrip("/")
        self.url = self.base + "/chat/completions"
        self.model = model
        self.timeout = timeout

    def _models(self, timeout: float = 3.0) -> list[str]:
        candidates = [self.base]
        if self.base == "http://127.0.0.1:1234/v1" and "http://127.0.0.1:11434/v1" not in candidates:
            candidates.append("http://127.0.0.1:11434/v1")
        last_exc = None
        for base in candidates:
            try:
                r = httpx.get(base + "/models", timeout=timeout)
                r.raise_for_status()
                self.base = base
                self.url = self.base + "/chat/completions"
                return [m["id"] for m in r.json().get("data", [])]
            except Exception as e:
                last_exc = e
                continue
        if last_exc:
            raise last_exc
        return []

    def ping(self) -> tuple[bool, str]:
        try:
            models = self._models(timeout=2.0)
        except Exception as e:
            return False, f"no server at {self.base} ({type(e).__name__})"
        if not models:
            return False, "server is running but no model is loaded"
        if self.model and self.model not in models:
            return False, f"model '{self.model}' not loaded (loaded: {', '.join(models[:3])})"
        return True, self.model or models[0]

    def _complete(self, prompt: str) -> str:
        if not self.model:  # auto-detect whatever model is loaded
            models = self._models()
            if not models:
                raise RuntimeError("no model loaded in the local server")
            self.model = models[0]
        r = httpx.post(
            self.url, timeout=self.timeout,
            json={"model": self.model, "temperature": 0.1,
                  "messages": [{"role": "user", "content": prompt}]},
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"]


class LlamaCppClient(LLMClient):
    """Gemma GGUF loaded in-process via llama-cpp-python. No server, no network."""
    name = "llamacpp"

    def __init__(self, gguf_path: str):
        try:
            from llama_cpp import Llama  # type: ignore
        except ImportError as e:  # pragma: no cover
            raise ConfigError("pip install llama-cpp-python to use LLM_BACKEND=llamacpp") from e
        self.llm = Llama(model_path=gguf_path, n_ctx=2048, verbose=False)

    def _complete(self, prompt: str) -> str:  # pragma: no cover - needs a model file
        out = self.llm.create_chat_completion(
            messages=[{"role": "user", "content": prompt}], temperature=0.1, max_tokens=120)
        return out["choices"][0]["message"]["content"]


class GeminiGemmaClient(LLMClient):
    """Gemma served by the Google Generative AI API. Demo mode only."""
    name = "gemini"

    def __init__(self, api_key: str, model: str, timeout: float = 60.0):
        self.api_key, self.model, self.timeout = api_key, model, timeout

    def ping(self) -> tuple[bool, str]:
        return bool(self.api_key), self.model  # no network call: free-tier quota is small

    def _complete(self, prompt: str) -> str:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent"
        r = httpx.post(url, params={"key": self.api_key}, timeout=self.timeout,
                       json={"contents": [{"parts": [{"text": prompt}]}]})
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]


class SafeClient(LLMClient):
    """Wraps a model backend; if it fails, falls back to rules so scans never crash."""

    def __init__(self, inner: LLMClient):
        self.inner, self.fallback = inner, HeuristicClient()
        self.name = inner.name
        self.last_error: str | None = None

    def ping(self) -> tuple[bool, str]:
        return self.inner.ping()

    def _complete(self, prompt: str) -> str:  # pragma: no cover - unused
        return self.inner._complete(prompt)

    def classify(self, meta, snippet, examples):
        try:
            result = self.inner.classify(meta, snippet, examples)
            self.last_error = None
            return result
        except Exception as e:  # network down, model missing, bad output
            self.last_error = f"{type(e).__name__}: {e}"
            result = self.fallback.classify(meta, snippet, examples)
            result["confidence"] = min(result["confidence"], 0.6)
            return result


def build_client(s: Settings) -> LLMClient:
    s.validate()
    if s.llm_backend == "heuristic":
        return HeuristicClient()
    if s.llm_backend == "openai":
        return SafeClient(OpenAICompatClient(s.llm_base_url, s.llm_model))
    if s.llm_backend == "llamacpp":
        return SafeClient(LlamaCppClient(s.gguf_path))
    return SafeClient(GeminiGemmaClient(s.google_api_key, s.gemma_model))
