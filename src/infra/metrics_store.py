# File: strc/infra/metrics_store.py

from __future__ import annotations

import threading
from collections import defaultdict
from typing import Any


class MetricsStore:
    """
    Lightweight in-memory metrics registry.

    Provides counters and timing aggregation for:
    - agent runs
    - node executions
    - LLM calls
    - action executions
    """

    # Singleton instance
    _instance: "MetricsStore | None" = None

    # Lock for singleton creation
    _lock = threading.Lock()

    def __new__(cls) -> "MetricsStore":
        """Ensure only one metrics store exists per process."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._init_state()
        return cls._instance

    def _init_state(self) -> None:
        """Initialize all metric containers."""

        # Lock protecting metric updates
        self._metrics_lock = threading.Lock()

        # Agent run counters
        self.agent_runs_total = 0
        self.agent_runs_success_total = 0
        self.agent_runs_failed_total = 0

        # Node metrics
        self.node_counts = defaultdict(int)
        self.node_failures = defaultdict(int)
        self.node_duration_ms_total = defaultdict(float)

        # LLM metrics
        self.llm_calls_total = defaultdict(int)
        self.llm_failures_total = defaultdict(int)
        self.llm_duration_ms_total = defaultdict(float)

        # Action execution metrics
        self.action_counts = defaultdict(int)
        self.action_failures = defaultdict(int)
        self.action_duration_ms_total = defaultdict(float)

    def increment_agent_run(self, success: bool) -> None:
        """Record completion of an agent run."""

        with self._metrics_lock:
            self.agent_runs_total += 1

            if success:
                self.agent_runs_success_total += 1
            else:
                self.agent_runs_failed_total += 1

    def record_node(self, node_name: str, duration_ms: float, success: bool) -> None:
        """Record node execution metrics."""

        with self._metrics_lock:
            self.node_counts[node_name] += 1
            self.node_duration_ms_total[node_name] += duration_ms

            if not success:
                self.node_failures[node_name] += 1

    def record_llm(self, schema_name: str, duration_ms: float, success: bool) -> None:
        """Record LLM call metrics."""

        with self._metrics_lock:
            self.llm_calls_total[schema_name] += 1
            self.llm_duration_ms_total[schema_name] += duration_ms

            if not success:
                self.llm_failures_total[schema_name] += 1

    def record_action(self, action_type: str, duration_ms: float, success: bool) -> None:
        """Record action execution metrics."""

        with self._metrics_lock:
            self.action_counts[action_type] += 1
            self.action_duration_ms_total[action_type] += duration_ms

            if not success:
                self.action_failures[action_type] += 1

    def snapshot(self) -> dict[str, Any]:
        """Return JSON-serializable snapshot of all metrics."""

        with self._metrics_lock:

            node_metrics = {}

            # Compute node statistics
            for node_name, count in self.node_counts.items():
                total_duration = self.node_duration_ms_total.get(node_name, 0.0)

                node_metrics[node_name] = {
                    "count": count,
                    "failures": self.node_failures.get(node_name, 0),
                    "total_duration_ms": round(total_duration, 2),
                    "avg_duration_ms": round(total_duration / count, 2) if count else 0.0,
                }

            llm_metrics = {}

            # Compute LLM statistics
            for schema_name, count in self.llm_calls_total.items():
                total_duration = self.llm_duration_ms_total.get(schema_name, 0.0)

                llm_metrics[schema_name] = {
                    "count": count,
                    "failures": self.llm_failures_total.get(schema_name, 0),
                    "total_duration_ms": round(total_duration, 2),
                    "avg_duration_ms": round(total_duration / count, 2) if count else 0.0,
                }

            action_metrics = {}

            # Compute action execution statistics
            for action_type, count in self.action_counts.items():
                total_duration = self.action_duration_ms_total.get(action_type, 0.0)

                action_metrics[action_type] = {
                    "count": count,
                    "failures": self.action_failures.get(action_type, 0),
                    "total_duration_ms": round(total_duration, 2),
                    "avg_duration_ms": round(total_duration / count, 2) if count else 0.0,
                }

            return {
                "agent_runs": {
                    "total": self.agent_runs_total,
                    "success": self.agent_runs_success_total,
                    "failed": self.agent_runs_failed_total,
                },
                "nodes": node_metrics,
                "llm": llm_metrics,
                "actions": action_metrics,
            }