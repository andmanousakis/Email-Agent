# File: src/infra/agent_api_client.py

from __future__ import annotations
import httpx
from utils.config_loader import ConfigLoader


class AgentApiClient:
    """
    Small API client used by the Streamlit UI to call backend endpoints.
    """

    def __init__(self) -> None:
        """
        Load API configuration and initialize request timeouts.
        """

        # Load API configuration.
        config = ConfigLoader("config-agent.yaml").load()
        api_cfg = config["API_CLIENT"]

        # Store base API URL.
        self.base_url = api_cfg["BASE_URL"]

        # Configure health timeout.
        self.health_timeout = httpx.Timeout(api_cfg["HEALTH_ENDPOINT_TIMEOUT"])

        # Configure run timeout.
        self.run_timeout = httpx.Timeout(api_cfg["RUN_AGENT_TIMEOUT"])

        # Reuse run timeout for metrics endpoint.
        self.metrics_timeout = httpx.Timeout(api_cfg["RUN_AGENT_TIMEOUT"])

    def health(self) -> dict:
        """
        Call the backend health endpoint.
        """

        # Send GET request to health endpoint.
        response = httpx.get(
            f"{self.base_url}/health",
            timeout=self.health_timeout,
        )

        # Raise on non-2xx response.
        response.raise_for_status()

        # Return parsed JSON payload.
        return response.json()

    def run(self, thread: dict) -> dict:
        """
        Run the email agent for a given thread.
        """

        # Send POST request to run endpoint.
        response = httpx.post(
            f"{self.base_url}/agent/run",
            json=thread,
            timeout=self.run_timeout,
        )

        # Raise on non-2xx response.
        response.raise_for_status()

        # Extract response payload.
        payload = response.json()

        # Return only the result object.
        return payload["result"]

    def metrics(self) -> dict:
        """
        Retrieve backend observability metrics.
        """

        # Send GET request to metrics endpoint.
        response = httpx.get(
            f"{self.base_url}/observability/metrics",
            timeout=self.metrics_timeout,
        )

        # Raise on non-2xx response.
        response.raise_for_status()

        # Return parsed JSON payload.
        return response.json()