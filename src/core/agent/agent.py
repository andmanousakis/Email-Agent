# File: src/core/agent/agent.py

from __future__ import annotations

import logging
import time
import uuid

from langgraph.graph import END, StateGraph

from src.core.agent.nodes import DraftNode, PlanActionsNode, RetrieveMemoryNode, SummarizeNode, TriageNode
from src.core.agent.state import AgentState
from utils.gemini_client import GeminiClient
from src.infra.metrics_store import MetricsStore


# Create the module logger.
logger = logging.getLogger(__name__)

# Reduce noisy httpx logging.
logging.getLogger("httpx").setLevel(logging.WARNING)

# Reduce noisy urllib3 logging.
logging.getLogger("urllib3").setLevel(logging.WARNING)

# Reduce noisy google client logging.
logging.getLogger("google").setLevel(logging.WARNING)

# Reduce noisy google genai logging.
logging.getLogger("google_genai").setLevel(logging.WARNING)


class EmailGraphAgent:
    """
    Build and execute the email-agent workflow graph.

    The workflow performs triage, summarization, long-term memory retrieval,
    draft generation, and action planning for a single email thread.
    """

    def __init__(self):
        """
        Initialize the workflow nodes and shared model client.
        """

        # Create the shared language model client.
        llm = GeminiClient()

        # Create the triage node.
        self.triage = TriageNode(llm)

        # Create the summarization node.
        self.summarize = SummarizeNode(llm)

        # Create the memory retrieval node.
        self.memory = RetrieveMemoryNode()

        # Create the drafting node.
        self.draft = DraftNode(llm)

        # Create the action-planning node.
        self.plan = PlanActionsNode(llm)

    def computation_graph(self):
        """
        Create and compile the LangGraph workflow.
        """

        # Create the state graph.
        g = StateGraph(AgentState)

        # Register the triage node.
        g.add_node(self.triage.name, self.triage)

        # Register the summarization node.
        g.add_node(self.summarize.name, self.summarize)

        # Register the memory retrieval node.
        g.add_node(self.memory.name, self.memory)

        # Register the drafting node.
        g.add_node(self.draft.name, self.draft)

        # Register the action-planning node.
        g.add_node(self.plan.name, self.plan)

        # Set the triage node as the entry point.
        g.set_entry_point(self.triage.name)

        # Connect triage to summarization.
        g.add_edge(self.triage.name, self.summarize.name)

        # Connect summarization to memory retrieval.
        g.add_edge(self.summarize.name, self.memory.name)

        # Connect memory retrieval to drafting.
        g.add_edge(self.memory.name, self.draft.name)

        # Connect drafting to action planning.
        g.add_edge(self.draft.name, self.plan.name)

        # Connect action planning to graph end.
        g.add_edge(self.plan.name, END)

        # Compile and return the workflow graph.
        return g.compile()

    @classmethod
    def run(cls, thread) -> dict:
        """
        Run the compiled workflow on a single email thread.
        """

        # Create a short run identifier.
        run_id = uuid.uuid4().hex[:10]

        # Capture the start time.
        t0 = time.perf_counter()

        # Create metrics registry.
        metrics = MetricsStore()

        # Log the start of the workflow run.
        logger.info(
            "agent_run_start run_id=%s thread_id=%s subject=%r messages=%d",
            run_id,
            thread.thread_id,
            thread.subject,
            len(thread.messages),
        )

        try:
            # Create a fresh agent instance.
            builder = cls()

            # Compile the workflow graph.
            graph = builder.computation_graph()

            # Create the initial workflow state.
            state = AgentState(thread=thread, run_id=run_id)

            # Execute the workflow graph.
            final_state = graph.invoke(state)

            # Compute the total runtime in milliseconds.
            dt_ms = (time.perf_counter() - t0) * 1000.0

            # Increment successful agent run metrics.
            metrics.increment_agent_run(success=True)

            # Log the successful workflow completion.
            logger.info(
                "agent_run_end run_id=%s thread_id=%s duration_ms=%.2f",
                run_id,
                thread.thread_id,
                dt_ms,
            )

            # Validate and serialize the final state.
            return AgentState.model_validate(final_state).model_dump(by_alias=True)

        except Exception:
            # Compute the total runtime in milliseconds.
            dt_ms = (time.perf_counter() - t0) * 1000.0

            # Increment failed agent run metrics.
            metrics.increment_agent_run(success=False)

            # Log the failed workflow completion.
            logger.exception(
                "agent_run_error run_id=%s thread_id=%s duration_ms=%.2f",
                run_id,
                getattr(thread, "thread_id", "unknown"),
                dt_ms,
            )

            # Re-raise the exception after logging.
            raise