from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException

from src.core.agent.agent import EmailGraphAgent
from src.core.agent.state import EmailThread


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/agent", tags=["email agent"])


@router.post("/run")
def run_agent(thread: EmailThread):
    logger.info(
        "run_agent_request thread_id=%s subject=%r messages=%d",
        thread.thread_id,
        thread.subject,
        len(thread.messages),
    )

    try:
        result = EmailGraphAgent.run(thread)
        return {
            "status": "success",
            "result": result,
        }
    except Exception as exc:
        logger.exception("run_agent_failed thread_id=%s", thread.thread_id)
        raise HTTPException(status_code=500, detail=str(exc))