# File: src/infra/memory_store.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.config_loader import ConfigLoader


class MemoryStore:
    """
    JSON-backed store for long-term agent memory.

    This component persists structured memory such as user preferences,
    contacts, organizational facts, and interaction history. The storage
    location is resolved from the configuration file.
    """

    # Initialize the memory store and resolve the memory file path.
    def __init__(self) -> None:
        # Load the memory store configuration.
        config = ConfigLoader("config-memory-store.yaml").load()

        # Resolve the project root directory.
        root_dir = Path(__file__).resolve().parents[2]

        # Resolve the email data path from configuration.
        self.email_data_path = root_dir / config["EMAIL_DATA_PATH"]

        # Resolve the memory data path from configuration.
        self.memory_data_path = root_dir / config["MEMORY_DATA_PATH"]

    def _default_memory(self) -> dict[str, Any]:
        """
        Return the default in-memory structure used when no memory file exists.
        """
        # Return the empty memory structure.
        return {
            "user_preferences": {},
            "contacts": [],
            "org_facts": {},
            "interaction_history": [],
        }

    def _load(self) -> dict[str, Any]:
        """
        Load the memory document from disk.
        """
        # Return the default structure if the memory file does not exist.
        if not self.memory_data_path.exists():
            return self._default_memory()

        # Read and parse the JSON memory file.
        memory = json.loads(self.memory_data_path.read_text(encoding="utf-8"))

        # Ensure interaction history exists in older files.
        memory.setdefault("interaction_history", [])

        # Return the loaded memory document.
        return memory

    def _save(self, memory: dict[str, Any]) -> None:
        """
        Persist the memory document to disk.
        """
        # Write the updated memory document to disk.
        self.memory_data_path.write_text(json.dumps(memory, ensure_ascii=False, indent=2), encoding="utf-8")

    def get_user_preferences(self) -> dict[str, Any]:
        """
        Retrieve stored user preferences.
        """
        # Load the full memory document.
        memory = self._load()

        # Return the user preferences section.
        return memory.get("user_preferences", {})

    def get_contact_by_email(self, email: str) -> dict[str, Any]:
        """
        Retrieve a stored contact by email address.
        """
        # Load the memory document.
        memory = self._load()

        # Iterate through stored contacts.
        for contact in memory.get("contacts", []):
            # Return the matching contact when the email matches.
            if contact.get("email") == email:
                return contact

        # Return an empty object when no contact is found.
        return {}

    def get_org_facts(self) -> dict[str, Any]:
        """
        Retrieve stored organizational facts.
        """
        # Load the memory document.
        memory = self._load()

        # Return the organizational facts section.
        return memory.get("org_facts", {})

    def update_user_preferences(self, updates: dict[str, Any]) -> None:
        """
        Merge new preference values into stored user preferences.
        """
        # Load the memory document.
        memory = self._load()

        # Resolve the current user preferences.
        current_preferences = memory.get("user_preferences", {})

        # Merge the incoming updates.
        current_preferences.update(updates)

        # Store the merged preferences back into memory.
        memory["user_preferences"] = current_preferences

        # Persist the updated memory document.
        self._save(memory)

    def append_interaction(self, record: dict[str, Any]) -> None:
        """
        Append an interaction record to the memory history.
        """
        # Load the memory document.
        memory = self._load()

        # Resolve the current interaction history.
        history = memory.get("interaction_history", [])

        # Append the new interaction record.
        history.append(record)

        # Store the updated history back into memory.
        memory["interaction_history"] = history

        # Persist the updated memory document.
        self._save(memory)

    def update_from_approved_actions(self, thread_id: str, thread_subject: str, approved_actions: list[dict]) -> None:
        """
        Derive lightweight memory updates from approved actions.

        This method updates user preferences using simple deterministic
        heuristics and stores a history record of the approved actions.
        """
        # Initialize the preference updates dictionary.
        preference_updates: dict[str, Any] = {}

        # Iterate through approved actions.
        for action in approved_actions:
            # Resolve the action type.
            action_type = action.get("type")

            # Resolve the action payload.
            payload = action.get("payload", {}) or {}

            # Derive preference updates from approved email actions.
            if action_type == "send_email":
                # Resolve the approved email body.
                body = payload.get("body", "") or ""

                # Count the body words.
                word_count = len(body.split())

                # Infer a reply length preference.
                preference_updates["reply_length"] = "concise" if word_count <= 120 else "detailed"

                # Infer a stable signature when the body contains one.
                if "\n\n" in body:
                    # Resolve the final paragraph as a candidate signature.
                    candidate_signature = body.strip().split("\n\n")[-1].strip()

                    # Persist the signature when it is short enough to be meaningful.
                    if 0 < len(candidate_signature) <= 60:
                        preference_updates["signature"] = candidate_signature

            # Derive preference updates from approved calendar actions.
            if action_type == "create_calendar_event":
                # Mark that calendar suggestions are acceptable.
                preference_updates["allow_calendar_suggestions"] = True

            # Derive preference updates from approved task actions.
            if action_type == "create_task":
                # Mark that task suggestions are acceptable.
                preference_updates["allow_task_suggestions"] = True

        # Persist any derived preference updates.
        if preference_updates:
            self.update_user_preferences(preference_updates)

        # Build the interaction history record.
        interaction_record = {
            "thread_id": thread_id,
            "thread_subject": thread_subject,
            "approved_actions": approved_actions,
        }

        # Persist the interaction history record.
        self.append_interaction(interaction_record)