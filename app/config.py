from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


class ConfigError(RuntimeError):
    """Raised when the environment is configured in an unsafe or invalid way."""


def _flag(name: str, default: bool) -> bool:
    return os.getenv(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    watch_dir: Path
    db_path: Path
    llm_backend: str = "openai"         # openai | llamacpp | gemini | heuristic (rules, no AI)
    dry_run: bool = True
    demo_mode: bool = False
    auto_watch: bool = False
    confidence_threshold: float = 0.6
    poll_seconds: float = 5.0
    settle_seconds: float = 2.0
    snippet_bytes: int = 1024
    # OpenAI-compatible local server (LM Studio, llama.cpp server, vLLM...)
    llm_base_url: str = "http://127.0.0.1:1234/v1"
    llm_model: str = ""                 # empty = use whichever model the local server has loaded
    # llama-cpp-python (fully offline)
    gguf_path: str = ""
    # Gemma through the Google Generative AI API (demo only)
    google_api_key: str = field(default="", repr=False)
    gemma_model: str = "gemma-4-31b-it"

    @classmethod
    def from_env(cls) -> "Settings":
        s = cls(
            watch_dir=Path(os.getenv("WATCH_DIR", "./watched")).expanduser(),
            db_path=Path(os.getenv("DB_PATH", "./slothsort.db")).expanduser(),
            llm_backend=os.getenv("LLM_BACKEND", "openai").lower(),
            dry_run=_flag("DRY_RUN", True),
            demo_mode=_flag("DEMO_MODE", False),
            auto_watch=_flag("AUTO_WATCH", False),
            confidence_threshold=float(os.getenv("CONFIDENCE_THRESHOLD", "0.6")),
            poll_seconds=float(os.getenv("POLL_SECONDS", "5")),
            settle_seconds=float(os.getenv("SETTLE_SECONDS", "2")),
            llm_base_url=os.getenv("LLM_BASE_URL", "http://127.0.0.1:1234/v1"),
            llm_model=os.getenv("LLM_MODEL", ""),
            gguf_path=os.getenv("GGUF_PATH", ""),
            google_api_key=os.getenv("GOOGLE_API_KEY", ""),
            gemma_model=os.getenv("GEMMA_MODEL", "gemma-4-31b-it"),
        )
        s.validate()
        return s

    def validate(self) -> None:
        if self.llm_backend not in {"heuristic", "openai", "llamacpp", "gemini"}:
            raise ConfigError(f"Unknown LLM_BACKEND '{self.llm_backend}'.")
        if self.llm_backend == "gemini":
            if not self.demo_mode:
                raise ConfigError(
                    "LLM_BACKEND=gemini sends text to a network API, so it is only "
                    "allowed with DEMO_MODE=true (sample files only)."
                )
            if not self.google_api_key:
                raise ConfigError("LLM_BACKEND=gemini needs GOOGLE_API_KEY.")
        if self.llm_backend == "llamacpp" and not self.gguf_path:
            raise ConfigError("LLM_BACKEND=llamacpp needs GGUF_PATH.")
        if not 0.0 <= self.confidence_threshold <= 1.0:
            raise ConfigError("CONFIDENCE_THRESHOLD must be between 0 and 1.")
