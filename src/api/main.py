from __future__ import annotations

import logging

from fastapi import FastAPI

from src.api.routes.agent import router as run_agent_router
from src.api.routes.observability import router as observability_router


if not logging.getLogger().handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Email Agent API",
    version="1.0.0",
)


@app.on_event("startup")
def on_startup() -> None:
    logger.info("email_agent_api_startup")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


app.include_router(run_agent_router)
app.include_router(observability_router)