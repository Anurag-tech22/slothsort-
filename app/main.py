from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from .config import ConfigError, Settings
from .service import ServiceError, Sloth, public, seed_samples

STATIC = Path(__file__).parent / "static"


class CorrectBody(BaseModel):
    category: str


class ModeBody(BaseModel):
    dry_run: bool


def create_app(settings: Settings | None = None, sloth: Sloth | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    sloth = sloth or Sloth(settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.demo_mode and not any(sloth.root.iterdir()):
            seed_samples(sloth.root)
        if settings.auto_watch:
            sloth.start_watching()
        yield
        sloth.stop_watching()

    app = FastAPI(title="Slothsort", version="1.0.0", lifespan=lifespan)
    app.state.sloth = sloth

    def guard(fn, *args):
        try:
            return fn(*args)
        except ServiceError as e:
            raise HTTPException(e.status, str(e))
        except ValueError as e:  # UnsafePathError and friends
            raise HTTPException(400, str(e))

    @app.get("/", include_in_schema=False)
    def index():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/health")
    def health():
        return {"ok": True}

    @app.get("/api/state")
    def state():
        return sloth.state()

    @app.post("/api/mode")
    def set_mode(body: ModeBody):
        sloth.dry_run = body.dry_run
        return sloth.state()

    @app.post("/api/scan")
    def scan():
        return sloth.scan()

    @app.get("/api/actions")
    def actions(status: str | None = None, limit: int = Query(100, ge=1, le=500)):
        return [public(a) for a in sloth.store.list(status, limit)]

    @app.post("/api/actions/apply-confident")
    def apply_confident():
        return {"applied": sloth.apply_confident()}

    @app.post("/api/actions/{action_id}/approve")
    def approve(action_id: int):
        return guard(sloth.apply, action_id)

    @app.post("/api/actions/{action_id}/undo")
    def undo(action_id: int):
        return guard(sloth.undo, action_id)

    @app.post("/api/actions/{action_id}/skip")
    def skip(action_id: int):
        return guard(sloth.skip, action_id)

    @app.post("/api/actions/{action_id}/correct")
    def correct(action_id: int, body: CorrectBody):
        return guard(sloth.correct, action_id, body.category)

    @app.get("/api/actions/{action_id}/similar")
    def similar(action_id: int):
        return guard(sloth.similar_files, action_id)

    @app.get("/api/search")
    def search(q: str = Query(..., min_length=1, max_length=200)):
        return sloth.search(q)

    @app.post("/api/demo/seed")
    def demo_seed():
        if not settings.demo_mode:
            raise HTTPException(403, "Sample files can only be created when DEMO_MODE=true.")
        return {"created": seed_samples(sloth.root)}

    return app


def factory() -> FastAPI:
    """Used by `uvicorn app.main:factory --factory`. Fails loudly on bad config."""
    try:
        return create_app()
    except ConfigError as e:
        raise SystemExit(f"Configuration error: {e}")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(factory(), host="127.0.0.1", port=8000)
