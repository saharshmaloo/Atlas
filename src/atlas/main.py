"""ASGI entry point: uvicorn atlas.main:app."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from atlas.embedding_api import router as embedding_router
from atlas.hybrid import router as hybrid_router
from atlas.answers import router as answers_router
from atlas.database import database_url
from atlas.pdf_api import router as pdf_router
from atlas.passages import router as passages_router
from atlas.search import router as search_router
from atlas.sources import UploadLimitMiddleware, router as sources_router
from atlas.verification_api import router as verification_router
from atlas.vector_search import router as vector_router
from atlas.web_ingest import router as web_router
from atlas.workspaces import router


class HealthResponse(BaseModel):
    status: Literal["ok"]


def health() -> HealthResponse:
    """Report process liveness; this does not check external dependencies."""
    return HealthResponse(status="ok")


def create_app(url: str | URL | None = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.engine = create_engine(url or database_url(), pool_pre_ping=True)
        try:
            yield
        finally:
            app.state.engine.dispose()

    app = FastAPI(title="Atlas", version="0.1.0", lifespan=lifespan)
    app.add_api_route("/health", health, response_model=HealthResponse)
    app.include_router(router)
    app.include_router(sources_router)
    app.include_router(pdf_router)
    app.include_router(web_router)
    app.include_router(passages_router)
    app.include_router(search_router)
    app.include_router(answers_router)
    app.include_router(embedding_router)
    app.include_router(vector_router)
    app.include_router(hybrid_router)
    app.include_router(verification_router)
    app.add_middleware(UploadLimitMiddleware)
    static = Path(__file__).parent / "static"
    app.mount("/assets", StaticFiles(directory=static), name="assets")

    @app.get("/", include_in_schema=False)
    def workspace_ui():
        return FileResponse(static / "index.html")

    return app


app = create_app()
