# File: src/infra/mail_store.py

from __future__ import annotations

import json
from pathlib import Path

from utils.config_loader import ConfigLoader
from src.core.agent.state import EmailThread


class MailStore:
    """
    Loads email threads from a JSON file defined in config-ui.yaml.
    """

    def __init__(self):

        # Load UI config
        config = ConfigLoader("config-ui.yaml").load()

        # Path defined in config
        data_path = config["EMAIL_DATA_PATH"]

        # Resolve project root
        root_dir = Path(__file__).resolve().parents[2]

        # Full path to JSON file
        self.data_path = root_dir / data_path

    def _load_raw(self) -> dict:
        """Load raw JSON data."""
        return json.loads(self.data_path.read_text(encoding="utf-8"))

    def list_threads(self) -> list[dict]:
        """
        Return raw thread metadata for UI listing.
        """
        raw = self._load_raw()
        return raw.get("threads", [])

    def get_thread(self, thread_id: str) -> EmailThread:
        """
        Retrieve a thread and validate with EmailThread schema.
        """

        raw = self._load_raw()

        for t in raw.get("threads", []):
            if t.get("thread_id") == thread_id:
                return EmailThread.model_validate(t)

        raise ValueError(f"Thread not found: {thread_id}")