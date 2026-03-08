# File: src/infra/action_store.py

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from utils.config_loader import ConfigLoader



class ActionStore:

    """
    Define a small helper store for mock execution outputs.
    """

    def __init__(self) -> None:

        """
        Initialize the store and resolve the data directory.
        """

        # Load UI config.
        config = ConfigLoader("config-action-store.yaml").load()

        # Resolve project root from this file location.
        root_dir = Path(__file__).resolve().parents[2]

        # Resolve the main email data path from config.
        email_data_path = root_dir / config["EMAIL_DATA_PATH"]

        # Use the same data directory for mock execution artifacts.
        self.data_dir = email_data_path.parent

    def _path(self, filename: str) -> Path:

        """
        Build the full path for a given mock artifact file.
        """

        # Return the file path inside the data directory.
        return self.data_dir / filename

    def _read_list(self, filename: str) -> list[dict[str, Any]]:

        """
        Read an existing JSON list file or return an empty list.
        """

        # Resolve the target file path.
        path = self._path(filename)

        # Return an empty list if the file does not exist yet.
        if not path.exists():
            return []

        # Read and parse the JSON file contents.
        return json.loads(path.read_text(encoding="utf-8"))

    def append(self, filename: str, record: dict[str, Any]) -> None:

        """
        Append one record to a JSON list file.
        """

        # Load existing records from disk.
        records = self._read_list(filename)

        # Add the new record at the end.
        records.append(record)

        # Resolve the target file path.
        path = self._path(filename)

        # Write the updated records back to disk.
        path.write_text(
            json.dumps(records, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )