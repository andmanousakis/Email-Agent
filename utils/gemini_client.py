# File: utils/gemini_client.py

from __future__ import annotations

import logging
import os
import time
from typing import Optional, Type

from google import genai
from pydantic import BaseModel

from src.infra.metrics_store import MetricsStore
from utils.config_loader import ConfigLoader


logger = logging.getLogger(__name__)


class GeminiClient:
    """
    Thin wrapper around the Gemini API with observability.

    Adds:
    - structured logging
    - latency tracking
    - metrics collection
    """

    def __init__(self):

        # Read API key from environment
        api_key = os.getenv("GEMINI_API_KEY")

        if not api_key:
            raise ValueError("GEMINI_API_KEY environment variable not set")

        # Create Gemini client
        self.client = genai.Client(api_key=api_key)

        # Load model configuration
        config = ConfigLoader("config-models.yaml").load()
        self.gen_cfg = config["GENERATION_MODEL"]

        self.model = self.gen_cfg["NAME"]
        self.temperature = float(self.gen_cfg.get("TEMPERATURE", 0.2))
        self.top_p = float(self.gen_cfg.get("TOP_P", 0.9))
        self.max_tokens = int(self.gen_cfg.get("MAX_TOKENS", 512))

        # Initialize metrics registry
        self.metrics = MetricsStore()

        logger.info("gemini_client_initialized model=%s", self.model)

    def generate_structured(
        self,
        prompt: str,
        schema: Type[BaseModel],
        run_id: Optional[str] = None,
        thread_id: Optional[str] = None,
        node_name: Optional[str] = None,
    ) -> BaseModel:
        """
        Generate structured JSON output from Gemini.

        Adds tracing metadata and metrics collection.
        """

        schema_name = schema.__name__

        logger.info(
            "llm_call_start run_id=%s thread_id=%s node=%s model=%s schema=%s prompt_chars=%d",
            run_id,
            thread_id,
            node_name,
            self.model,
            schema_name,
            len(prompt),
        )

        # Capture start time
        t0 = time.perf_counter()

        try:

            # Execute LLM call
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
                config={
                    "temperature": self.temperature,
                    "top_p": self.top_p,
                    "max_output_tokens": self.max_tokens,
                    "response_mime_type": "application/json",
                    "response_schema": schema,
                },
            )

        except Exception:

            logger.exception(
                "llm_call_failed run_id=%s thread_id=%s node=%s schema=%s",
                run_id,
                thread_id,
                node_name,
                schema_name,
            )

            self.metrics.record_llm(schema_name, 0, False)

            raise

        # Compute duration
        duration_ms = (time.perf_counter() - t0) * 1000

        if getattr(response, "parsed", None) is not None:

            logger.info(
                "llm_call_end run_id=%s thread_id=%s node=%s schema=%s duration_ms=%.2f",
                run_id,
                thread_id,
                node_name,
                schema_name,
                duration_ms,
            )

            # Warn for slow responses
            if duration_ms > 10000:
                logger.warning(
                    "llm_call_slow run_id=%s node=%s schema=%s duration_ms=%.2f",
                    run_id,
                    node_name,
                    schema_name,
                    duration_ms,
                )

            self.metrics.record_llm(schema_name, duration_ms, True)

            return response.parsed

        raise ValueError(
            f"Gemini did not return parsed structured output for schema {schema_name}."
        )