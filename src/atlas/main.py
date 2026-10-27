"""ASGI entry point: uvicorn atlas.main:app."""

from typing import Literal

from fastapi import FastAPI
from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: Literal["ok"]


app = FastAPI(title="Atlas", version="0.1.0")


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Report process liveness; this does not check external dependencies."""
    return HealthResponse(status="ok")
