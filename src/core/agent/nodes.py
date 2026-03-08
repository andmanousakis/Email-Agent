# File: src/core/agent/nodes.py

from __future__ import annotations

import json
import logging
import time
from typing import List

from src.core.agent.state import AgentState, DraftReply, ExecutionEvent, ProposedAction, ProposedActionsResult, ThreadSummary, TriageResult
from src.infra.memory_store import MemoryStore
from src.infra.metrics_store import MetricsStore
from utils.gemini_client import GeminiClient


logger = logging.getLogger(__name__)


class BaseNode:
    """
    Base interface for all agent workflow nodes.

    Each node receives the current agent state and returns a partial
    state update that LangGraph merges into the global state.
    """

    # Define the node name attribute.
    name: str

    def __init__(self) -> None:
        """
        Initialize shared observability dependencies.
        """

        # Create shared metrics registry.
        self.metrics = MetricsStore()

    def __call__(self, state: AgentState) -> dict:
        """
        Execute the node with structured logging and metrics.
        """

        # Capture start time.
        t0 = time.perf_counter()

        # Log node start.
        logger.info(
            "node_start run_id=%s thread_id=%s node=%s",
            state.run_id,
            state.thread.thread_id,
            self.name,
        )

        try:
            # Execute node-specific logic.
            updates = self._run(state)

            # Compute node duration.
            duration_ms = (time.perf_counter() - t0) * 1000.0

            # Record successful node execution.
            self.metrics.record_node(self.name, duration_ms, success=True)

            # Build success execution event.
            event = ExecutionEvent(
                step=self.name,
                status="success",
                detail=f"{self.name} completed",
                duration_ms=duration_ms,
                metadata={
                    "run_id": state.run_id,
                    "thread_id": state.thread.thread_id,
                },
            )

            # Merge the execution event into the returned updates.
            updates["execution_log"] = list(state.execution_log) + [event]

            # Log node completion.
            logger.info(
                "node_end run_id=%s thread_id=%s node=%s duration_ms=%.2f status=success",
                state.run_id,
                state.thread.thread_id,
                self.name,
                duration_ms,
            )

            # Return the instrumented updates.
            return updates

        except Exception as exc:
            # Compute node duration.
            duration_ms = (time.perf_counter() - t0) * 1000.0

            # Record failed node execution.
            self.metrics.record_node(self.name, duration_ms, success=False)

            # Log node failure.
            logger.exception(
                "node_error run_id=%s thread_id=%s node=%s duration_ms=%.2f error=%s",
                state.run_id,
                state.thread.thread_id,
                self.name,
                duration_ms,
                str(exc),
            )

            # Re-raise the original exception.
            raise

    def _run(self, state: AgentState) -> dict:
        """
        Execute the node-specific logic.
        """

        raise NotImplementedError


class RetrieveMemoryNode(BaseNode):
    """
    Retrieve long-term memory relevant to the current email thread.

    This node loads persisted user preferences, attempts to resolve the
    external contact from the thread participants, and fetches stored
    organizational facts for downstream drafting and action planning.
    """

    # Define the graph node name.
    name = "retrieve_memory"

    def __init__(self) -> None:
        """
        Initialize the memory retrieval node.

        This constructor creates the JSON-backed long-term memory store
        used during workflow execution.
        """

        # Initialize shared base dependencies.
        super().__init__()

        # Create the long-term memory store.
        self.memory_store = MemoryStore()

    def _run(self, state: AgentState) -> dict:
        """
        Retrieve relevant long-term memory for the current thread.

        The node fetches user preferences, resolves a matching contact
        from the non-user participants in the thread, and loads stored
        organizational facts.
        """

        # Retrieve persisted user preferences.
        user_preferences = self.memory_store.get_user_preferences()

        # Initialize contact memory as empty.
        contact = {}

        # Iterate through thread messages in reverse order.
        for msg in reversed(state.thread.messages):
            # Skip the user's own messages.
            if msg.from_.lower() == "andreas@company.com":
                continue

            # Try to resolve the sender from memory.
            contact = self.memory_store.get_contact_by_email(msg.from_)

            # Stop once a matching contact is found.
            if contact:
                break

        # Retrieve organizational facts.
        org_facts = self.memory_store.get_org_facts()

        # Return the retrieved memory to merge into state.
        return {
            "retrieved_preferences": user_preferences,
            "retrieved_contact": contact,
            "retrieved_org_facts": org_facts,
        }


class TriageNode(BaseNode):
    """
    Classify the incoming thread by urgency, category, and reply need.

    This node produces the first structured interpretation of the thread
    and provides the foundation for downstream summarization, memory use,
    drafting, and action planning.
    """

    # Define the graph node name.
    name = "triage"

    def __init__(self, llm: GeminiClient):
        """
        Initialize the triage node with the language model client.

        The model is used to classify the thread into the structured
        triage schema.
        """

        # Initialize shared base dependencies.
        super().__init__()

        # Store the language model client.
        self.llm = llm

    def _run(self, state: AgentState) -> dict:
        """
        Execute triage over the current email thread.

        The node serializes the thread, asks the model for a structured
        triage result, and returns it as a partial state update.
        """

        # Serialize the current thread for prompt construction.
        thread = state.thread.model_dump(by_alias=True)

        # Build the structured triage prompt.
        prompt = (
            "You are an email triage assistant.\n"
            "Return JSON ONLY matching this schema:\n"
            '{ "priority":"low|medium|high|urgent",'
            '  "category":"meeting|billing|incident",'
            '  "needs_reply": true|false,'
            '  "rationale":"string" }\n\n'
            f"Thread:\n{json.dumps(thread, ensure_ascii=False)}"
        )

        # Generate the structured triage result.
        triage = self.llm.generate_structured(
            prompt,
            TriageResult,
            run_id=state.run_id,
            thread_id=state.thread.thread_id,
            node_name=self.name,
        )

        # Return the triage update.
        return {"triage": triage}


class SummarizeNode(BaseNode):
    """
    Summarize the thread into key points and the main ask.

    This node distills the conversation after triage so later steps can
    reason over a compact structured representation instead of only the
    raw thread content.
    """

    # Define the graph node name.
    name = "summarize"

    def __init__(self, llm: GeminiClient):
        """
        Initialize the summarization node with the language model client.

        The model is used to produce a compact structured summary of the
        thread.
        """

        # Initialize shared base dependencies.
        super().__init__()

        # Store the language model client.
        self.llm = llm

    def _run(self, state: AgentState) -> dict:
        """
        Summarize the email thread using the triage context.

        The node requires triage to be present and returns a structured
        thread summary as a partial state update.
        """

        # Validate that triage has already been computed.
        if state.triage is None:
            raise ValueError("SummarizeNode requires triage results.")

        # Serialize the current thread for prompt construction.
        thread = state.thread.model_dump(by_alias=True)

        # Serialize the triage result for prompt construction.
        triage = state.triage.model_dump()

        # Build the structured summarization prompt.
        prompt = (
            "Summarize this email thread.\n"
            "Return JSON ONLY:\n"
            '{ "key_points":["string", "..."], "ask":"string|null" }\n\n'
            f"Triage:\n{json.dumps(triage, ensure_ascii=False)}\n\n"
            f"Thread:\n{json.dumps(thread, ensure_ascii=False)}"
        )

        # Generate the structured summary result.
        summary = self.llm.generate_structured(
            prompt,
            ThreadSummary,
            run_id=state.run_id,
            thread_id=state.thread.thread_id,
            node_name=self.name,
        )

        # Return the summary update.
        return {"summary": summary}


class DraftNode(BaseNode):
    """
    Draft a reply using thread context, summary, and retrieved memory.

    This node uses both short-term workflow state and long-term memory to
    generate a contextual reply aligned with user preferences, contact
    information, and organizational policies.
    """

    # Define the graph node name.
    name = "draft"

    def __init__(self, llm: GeminiClient):
        """
        Initialize the drafting node with the language model client.

        The node also defines the default user signature appended to the
        generated reply when missing.
        """

        # Initialize shared base dependencies.
        super().__init__()

        # Store the language model client.
        self.llm = llm

        # Define the default signature.
        self.signature = "Best,\nAndreas"

    def _run(self, state: AgentState) -> dict:
        """
        Draft a structured reply for the current thread.

        The node requires triage to be present and enriches the prompt
        with retrieved preferences, contact memory, and organization
        facts before generating the reply.
        """

        # Validate that triage has already been computed.
        if state.triage is None:
            raise ValueError("DraftNode requires triage results.")

        # Serialize the current thread for prompt construction.
        thread = state.thread.model_dump(by_alias=True)

        # Serialize the triage result for prompt construction.
        triage = state.triage.model_dump()

        # Serialize the summary if available.
        summary = state.summary.model_dump() if state.summary else None

        # Resolve retrieved user preferences.
        preferences = state.retrieved_preferences

        # Resolve retrieved contact information.
        contact = state.retrieved_contact

        # Resolve retrieved organizational facts.
        org_facts = state.retrieved_org_facts

        # Build the structured drafting prompt.
        prompt = (
            "Draft a professional reply.\n"
            "Return JSON ONLY:\n"
            '{ "subject":"string", "body":"string" }\n\n'
            f"Triage:\n{json.dumps(triage, ensure_ascii=False)}\n\n"
            f"Summary:\n{json.dumps(summary, ensure_ascii=False)}\n\n"
            f"UserPreferences:\n{json.dumps(preferences, ensure_ascii=False)}\n\n"
            f"ContactMemory:\n{json.dumps(contact, ensure_ascii=False)}\n\n"
            f"OrgFacts:\n{json.dumps(org_facts, ensure_ascii=False)}\n\n"
            f"Thread:\n{json.dumps(thread, ensure_ascii=False)}"
        )

        # Generate the structured draft result.
        draft = self.llm.generate_structured(
            prompt,
            DraftReply,
            run_id=state.run_id,
            thread_id=state.thread.thread_id,
            node_name=self.name,
        )

        # Ensure the reply subject uses a reply prefix.
        if not draft.subject.lower().startswith("re:"):
            draft.subject = f"Re: {state.thread.subject}"

        # Ensure the default signature is appended.
        if not draft.body.strip().endswith(self.signature):
            draft.body += f"\n\n{self.signature}"

        # Return the draft update.
        return {"draft": draft}


class PlanActionsNode(BaseNode):
    """
    Plan the next structured actions based on the analyzed thread.

    This node converts the thread understanding, generated draft, and
    retrieved memory into executable action proposals such as sending an
    email, creating a task, or scheduling a calendar event.
    """

    # Define the graph node name.
    name = "plan_actions"

    def __init__(self, llm: GeminiClient):
        """
        Initialize the action-planning node with the language model client.

        The model is used to generate schema-validated proposed actions
        for downstream review and execution.
        """

        # Initialize shared base dependencies.
        super().__init__()

        # Store the language model client.
        self.llm = llm

    def _run(self, state: AgentState) -> dict:
        """
        Plan the next actions for the current thread.

        The node requires triage to be present and uses the summary,
        draft, and retrieved long-term memory to produce structured
        action proposals.
        """

        # Validate that triage has already been computed.
        if state.triage is None:
            raise ValueError("PlanActionsNode requires triage results.")

        # Serialize the triage result for prompt construction.
        triage = state.triage.model_dump()

        # Serialize the summary if available.
        summary = state.summary.model_dump() if state.summary else None

        # Serialize the draft if available.
        draft = state.draft.model_dump() if state.draft else None

        # Resolve retrieved user preferences.
        preferences = state.retrieved_preferences

        # Resolve retrieved contact information.
        contact = state.retrieved_contact

        # Resolve retrieved organizational facts.
        org_facts = state.retrieved_org_facts

        # Build the structured action-planning prompt.
        prompt = (
            "Decide the next actions for this email.\n"
            "Return JSON ONLY matching this schema:\n"
            '{ "actions": ['
            '  {'
            '    "type":"send_email|create_calendar_event|create_task|none",'
            '    "label":"string",'
            '    "payload": {'
            '       "recipient":"string|null",'
            '       "subject":"string|null",'
            '       "body":"string|null",'
            '       "title":"string|null",'
            '       "description":"string|null",'
            '       "start_time":"string|null",'
            '       "end_time":"string|null",'
            '       "due_date":"string|null"'
            '    },'
            '    "requires_approval": boolean'
            '  }'
            '] }\n\n'
            "Rules:\n"
            "- Keep actions minimal.\n"
            "- Usually include send_email if a reply draft exists.\n"
            "- Include create_task only if follow-up work is needed.\n"
            "- For category=meeting, include create_calendar_event when the thread contains clear scheduling intent such as proposing, confirming, or requesting a meeting time.\n"
            "- Include create_calendar_event only if a meeting is clearly being arranged.\n"
            "- If type is none, use an empty payload.\n\n"
            f"Triage:\n{json.dumps(triage, ensure_ascii=False)}\n\n"
            f"Summary:\n{json.dumps(summary, ensure_ascii=False)}\n\n"
            f"Draft:\n{json.dumps(draft, ensure_ascii=False)}\n\n"
            f"UserPreferences:\n{json.dumps(preferences, ensure_ascii=False)}\n\n"
            f"ContactMemory:\n{json.dumps(contact, ensure_ascii=False)}\n\n"
            f"OrgFacts:\n{json.dumps(org_facts, ensure_ascii=False)}"
        )

        # Generate the structured actions result.
        result = self.llm.generate_structured(
            prompt,
            ProposedActionsResult,
            run_id=state.run_id,
            thread_id=state.thread.thread_id,
            node_name=self.name,
        )

        # Extract the proposed actions list.
        actions: List[ProposedAction] = result.actions

        # Return the proposed actions update.
        return {"proposed_actions": actions}
        """
        Plan the next actions for the current thread.

        The node requires triage to be present and uses the summary,
        draft, and retrieved long-term memory to produce structured
        action proposals.
        """
        # Validate that triage has already been computed.
        if state.triage is None:
            raise ValueError("PlanActionsNode requires triage results.")

        # Serialize the triage result for prompt construction.
        triage = state.triage.model_dump()

        # Serialize the summary if available.
        summary = state.summary.model_dump() if state.summary else None

        # Serialize the draft if available.
        draft = state.draft.model_dump() if state.draft else None

        # Resolve retrieved user preferences.
        preferences = state.retrieved_preferences

        # Resolve retrieved contact information.
        contact = state.retrieved_contact

        # Resolve retrieved organizational facts.
        org_facts = state.retrieved_org_facts

        # Build the structured action-planning prompt.
        prompt = (
            "Decide the next actions for this email.\n"
            "Return JSON ONLY matching this schema:\n"
            '{ "actions": ['
            '  {'
            '    "type":"send_email|create_calendar_event|create_task|none",'
            '    "label":"string",'
            '    "payload": {'
            '       "recipient":"string|null",'
            '       "subject":"string|null",'
            '       "body":"string|null",'
            '       "title":"string|null",'
            '       "description":"string|null",'
            '       "start_time":"string|null",'
            '       "end_time":"string|null",'
            '       "due_date":"string|null"'
            '    },'
            '    "requires_approval": boolean'
            '  }'
            '] }\n\n'
            "Rules:\n"
            "- Keep actions minimal.\n"
            "- Usually include send_email if a reply draft exists.\n"
            "- Include create_task only if follow-up work is needed.\n"
            "- For category=meeting, include create_calendar_event when the thread contains clear scheduling intent such as proposing, confirming, or requesting a meeting time.\n"
            "- Include create_calendar_event only if a meeting is clearly being arranged.\n"
            "- If type is none, use an empty payload.\n\n"
            f"Triage:\n{json.dumps(triage, ensure_ascii=False)}\n\n"
            f"Summary:\n{json.dumps(summary, ensure_ascii=False)}\n\n"
            f"Draft:\n{json.dumps(draft, ensure_ascii=False)}\n\n"
            f"UserPreferences:\n{json.dumps(preferences, ensure_ascii=False)}\n\n"
            f"ContactMemory:\n{json.dumps(contact, ensure_ascii=False)}\n\n"
            f"OrgFacts:\n{json.dumps(org_facts, ensure_ascii=False)}"
        )

        # Generate the structured actions result.
        result = self.llm.generate_structured(prompt, ProposedActionsResult)

        # Extract the proposed actions list.
        actions: List[ProposedAction] = result.actions

        # Return the proposed actions update.
        return {"proposed_actions": actions}