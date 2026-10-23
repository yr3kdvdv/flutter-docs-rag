"""FastAPI application exposing /health, /ready and /ask (docs/architecture.md §4)."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from flutter_rag.config import load_settings
from flutter_rag.errors import RagError


class AskRequest(BaseModel):
    question: str = Field(min_length=3, max_length=2000)


def create_app(config_path: str, runtime=None) -> FastAPI:
    state: dict = {"rt": runtime, "error": None}

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if state["rt"] is None:
            from flutter_rag.pipeline import Runtime, require_secrets
            from flutter_rag.runconfig import load_run_config

            try:
                settings = load_settings()
                require_secrets(settings, "ask")
                state["rt"] = Runtime(load_run_config(config_path), settings)
            except RagError as exc:  # keep serving /health; /ready reports why
                state["error"] = str(exc)
        yield
        if state["rt"] is not None:
            state["rt"].close()

    app = FastAPI(title="Flutter Docs RAG", version="0.1.0", lifespan=lifespan)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.get("/ready")
    def ready():
        rt = state["rt"]
        if rt is None:
            return JSONResponse({"status": "not_ready", "reason": state["error"]}, 503)
        points = rt.store.count()
        if points == 0:
            return JSONResponse({"status": "not_ready", "reason": "index is empty"}, 503)
        return {"status": "ready", "collection": rt.store.collection, "points": points}

    @app.post("/ask")
    def ask_endpoint(req: AskRequest):
        from flutter_rag.pipeline import ask

        rt = state["rt"]
        if rt is None:
            raise HTTPException(503, detail=state["error"] or "not ready")
        answer = ask(rt, req.question)
        if answer.status == "upstream_error":
            code = 429 if answer.error and answer.error["kind"] == "rate_limited" else 503
            return JSONResponse(answer.to_dict(), code)
        return answer.to_dict()

    return app
