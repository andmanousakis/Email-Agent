# File: src/api/routes/observability.py

from __future__ import annotations

from fastapi import APIRouter

from src.infra.metrics_store import MetricsStore


# Router responsible for observability endpoints.
router = APIRouter(prefix="/observability", tags=["observability"])


@router.get("/metrics")
def metrics_snapshot() -> dict:
    """
    Return a JSON snapshot of in-memory runtime metrics.

    This endpoint exposes aggregated metrics for:
    - agent runs
    - node executions
    - LLM calls
    - action executions
    """
    return MetricsStore().snapshot()