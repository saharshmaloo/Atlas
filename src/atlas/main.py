"""ASGI entry point: uvicorn atlas.main:app."""

from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.engine import URL

from atlas.database import database_url
from atlas.sources import UploadLimitMiddleware, router as sources_router
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
    app.add_middleware(UploadLimitMiddleware)
    return app


app = create_app()
