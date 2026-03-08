# File: src/infra/action_adapters.py

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from src.infra.action_store import ActionStore


class BaseAdapter:
    """
    Base adapter providing shared functionality for all action adapters.

    This class centralizes the construction of execution metadata that is
    common across all actions.
    """

    # Initialize the adapter with the shared action store.
    def __init__(self, store: ActionStore) -> None:
        # Store reference to the JSON-backed persistence layer.
        self.store = store

    # Build the common execution metadata shared by all adapters.
    def _base_record(
        self,
        thread_context: dict[str, Any],
        action_meta: dict[str, Any],
    ) -> dict[str, Any]:
        # Return the shared execution record fields.
        return {
            "executed_at": datetime.now(UTC).isoformat(),
            "thread_id": thread_context.get("thread_id"),
            "thread_subject": thread_context.get("thread_subject"),
            "action_type": action_meta.get("action_type"),
            "action_label": action_meta.get("action_label"),
        }


class EmailAdapter(BaseAdapter):
    """
    Adapter responsible for handling email-related actions.

    In this prototype the adapter does not actually send emails. Instead,
    it simulates email delivery by writing the email payload to a JSON file.
    This allows the agent workflow to demonstrate action execution while
    remaining completely safe and deterministic.
    """

    # Mock sending an email by persisting it to the action store.
    def send_email(
        self,
        payload: dict[str, Any],
        thread_context: dict[str, Any],
        action_meta: dict[str, Any],
    ) -> dict[str, Any]:
        # Build the base execution record.
        record = self._base_record(thread_context, action_meta)

        # Extend the record with email-specific fields.
        record.update(
            {
                "recipient": payload.get("recipient"),
                "subject": payload.get("subject"),
                "body": payload.get("body"),
            }
        )

        # Persist the simulated email.
        self.store.append("sent_emails.json", record)

        # Return a structured execution result.
        return {
            "status": "success",
            "message": "Mock email stored in sent_emails.json",
            "record": record,
        }


class TaskAdapter(BaseAdapter):
    """
    Adapter responsible for task creation actions.

    Instead of integrating with a real task management system (e.g.
    Jira, Asana, or Todoist), this adapter writes the task payload
    to a JSON file. This simulates how an agent would create tasks
    in an external system while keeping the prototype self-contained.
    """

    # Mock creating a task by persisting it to the action store.
    def create_task(
        self,
        payload: dict[str, Any],
        thread_context: dict[str, Any],
        action_meta: dict[str, Any],
    ) -> dict[str, Any]:
        # Build the base execution record.
        record = self._base_record(thread_context, action_meta)

        # Extend the record with task-specific fields.
        record.update(
            {
                "title": payload.get("title"),
                "description": payload.get("description"),
                "due_date": payload.get("due_date"),
            }
        )

        # Persist the simulated task.
        self.store.append("tasks.json", record)

        # Return a structured execution result.
        return {
            "status": "success",
            "message": "Mock task stored in tasks.json",
            "record": record,
        }


class CalendarAdapter(BaseAdapter):
    """
    Adapter responsible for calendar event creation actions.

    In a production environment this would integrate with a calendar
    provider such as Google Calendar or Microsoft Outlook. In this
    prototype the adapter records the event details into a JSON file,
    allowing the agent system to demonstrate tool execution without
    requiring external service integrations.
    """

    # Mock creating a calendar event by persisting it to the action store.
    def create_event(
        self,
        payload: dict[str, Any],
        thread_context: dict[str, Any],
        action_meta: dict[str, Any],
    ) -> dict[str, Any]:
        # Build the base execution record.
        record = self._base_record(thread_context, action_meta)

        # Extend the record with calendar-specific fields.
        record.update(
            {
                "title": payload.get("title"),
                "description": payload.get("description"),
                "start_time": payload.get("start_time"),
                "end_time": payload.get("end_time"),
            }
        )

        # Persist the simulated calendar event.
        self.store.append("calendar_events.json", record)

        # Return a structured execution result.
        return {
            "status": "success",
            "message": "Mock calendar event stored in calendar_events.json",
            "record": record,
        }