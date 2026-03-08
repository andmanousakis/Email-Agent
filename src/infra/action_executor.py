# File: src/infra/action_executor.py

from __future__ import annotations

import logging
import time

from src.infra.action_adapters import CalendarAdapter, EmailAdapter, TaskAdapter
from src.infra.action_store import ActionStore
from src.infra.metrics_store import MetricsStore


logger = logging.getLogger(__name__)


class ActionExecutor:
    """
    Coordinates execution of approved agent actions.

    This component receives actions produced by the agent,
    dispatches them to the appropriate adapter, and collects
    structured execution results. It acts as the orchestration
    layer between agent planning and tool execution.
    """

    def __init__(self) -> None:
        """
        Initialize the executor with adapters and metrics registry.
        """

        # Create the shared JSON-backed store.
        store = ActionStore()

        # Create the mock email adapter.
        self.email_adapter = EmailAdapter(store)

        # Create the mock task adapter.
        self.task_adapter = TaskAdapter(store)

        # Create the mock calendar adapter.
        self.calendar_adapter = CalendarAdapter(store)

        # Create the shared metrics registry.
        self.metrics = MetricsStore()

    def execute(self, action: dict, thread_context: dict) -> dict:
        """
        Execute a single approved action and return a structured result.
        """

        # Resolve the action type.
        action_type = action.get("type")

        # Resolve the action payload.
        payload = action.get("payload", {}) or {}

        # Build metadata describing the action.
        action_meta = {
            "action_type": action_type,
            "action_label": action.get("label"),
        }

        # Capture action start time.
        t0 = time.perf_counter()

        # Log action execution start.
        logger.info(
            "action_execute_start thread_id=%s action_type=%s label=%r",
            thread_context.get("thread_id"),
            action_type,
            action.get("label"),
        )

        try:
            # Route send_email actions.
            if action_type == "send_email":
                result = self.email_adapter.send_email(payload, thread_context, action_meta)

            # Route create_task actions.
            elif action_type == "create_task":
                result = self.task_adapter.create_task(payload, thread_context, action_meta)

            # Route create_calendar_event actions.
            elif action_type == "create_calendar_event":
                result = self.calendar_adapter.create_event(payload, thread_context, action_meta)

            # Handle unsupported actions explicitly.
            else:
                raise ValueError(f"Unsupported action type: {action_type}")

            # Compute action duration.
            duration_ms = (time.perf_counter() - t0) * 1000.0

            # Record successful action execution.
            self.metrics.record_action(action_type, duration_ms, success=True)

            # Log action execution completion.
            logger.info(
                "action_execute_end thread_id=%s action_type=%s duration_ms=%.2f status=success",
                thread_context.get("thread_id"),
                action_type,
                duration_ms,
            )

            # Return the structured execution output.
            return {
                "action_type": action_type,
                "label": action.get("label"),
                "result": result,
            }

        except Exception:
            # Compute action duration.
            duration_ms = (time.perf_counter() - t0) * 1000.0

            # Record failed action execution.
            self.metrics.record_action(action_type or "unknown", duration_ms, success=False)

            # Log action execution failure.
            logger.exception(
                "action_execute_error thread_id=%s action_type=%s duration_ms=%.2f",
                thread_context.get("thread_id"),
                action_type,
                duration_ms,
            )

            # Re-raise the original exception.
            raise

    def execute_many(self, actions: list[dict], thread_context: dict) -> list[dict]:
        """
        Execute multiple approved actions sequentially.
        """

        # Initialize the list that will collect execution results.
        results = []

        # Iterate through each approved action.
        for action in actions:
            # Execute the action through the single-action executor.
            result = self.execute(action, thread_context)

            # Append the execution result to the results list.
            results.append(result)

        # Return the collected execution results.
        return results