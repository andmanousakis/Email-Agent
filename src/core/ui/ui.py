# File: src/core/ui/ui.py

from __future__ import annotations

import logging
import pandas as pd
import streamlit as st

from src.infra.action_executor import ActionExecutor
from src.infra.agent_api_client import AgentApiClient
from src.infra.mail_store import MailStore
from src.infra.memory_store import MemoryStore
from src.infra.metrics_store import MetricsStore


# Configure basic logging once for the Streamlit process.
if not logging.getLogger().handlers:
    # Set the log level and format.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )

# Reduce noisy HTTP client logs in the UI process.
logging.getLogger("httpx").setLevel(logging.WARNING)


def get_thread_status(thread_id: str) -> str:
    """
    Derive a simple UI status label for a thread from session state.
    """

    # Resolve cached execution results.
    execution_results = st.session_state.get("execution_results", {}).get(thread_id, [])

    # Resolve cached agent results.
    agent_result = st.session_state.get("agent_results", {}).get(thread_id)

    # Return executed state when actions were approved and executed.
    if execution_results:
        return "Actions executed"

    # Return analyzed state when the agent has already run.
    if agent_result:
        return "Analyzed"

    # Default to not analyzed state.
    return "Not analyzed"


def get_combined_metrics(agent_client: AgentApiClient) -> dict:
    """
    Combine backend observability metrics with UI-side action metrics.

    Agent, node, and backend action metrics come from the API.
    UI-side action execution metrics come from the local Streamlit process.
    """

    # Initialize backend metrics.
    backend_metrics = {}

    try:
        # Retrieve backend metrics.
        backend_metrics = agent_client.metrics()
    except Exception:
        # Fallback to empty backend metrics on failure.
        backend_metrics = {}

    # Retrieve UI-local metrics from the Streamlit process.
    ui_metrics = MetricsStore().snapshot()

    # Resolve backend action metrics.
    backend_actions = backend_metrics.get("actions", {})

    # Resolve UI action metrics.
    ui_actions = ui_metrics.get("actions", {})

    # Merge actions, preferring UI values when the same action type exists.
    merged_actions = dict(backend_actions)
    merged_actions.update(ui_actions)

    # Store merged action metrics.
    backend_metrics["actions"] = merged_actions

    # Return combined metrics payload.
    return backend_metrics


def get_action_metrics_summary(metrics: dict) -> tuple[int, int]:
    """
    Compute total action executions and total action failures from action metrics.
    """

    # Resolve action metrics safely.
    actions = metrics.get("actions", {})

    # Compute total count across action types.
    total_count = sum(item.get("count", 0) for item in actions.values())

    # Compute total failures across action types.
    total_failures = sum(item.get("failures", 0) for item in actions.values())

    # Return aggregated values.
    return total_count, total_failures


def render_inbox(threads: list[dict]) -> str:
    """
    Render a simple Outlook-like inbox in the sidebar and return the selected thread id.
    """

    # Show the sidebar title.
    st.sidebar.title("Inbox")

    # Initialize selected thread.
    selected_thread_id = st.session_state.get("active_thread_id") or threads[0]["thread_id"]

    # Render each thread as a simple inbox row.
    for thread_dict in threads:
        # Resolve thread id.
        thread_id = thread_dict["thread_id"]

        # Resolve subject.
        subject = thread_dict["subject"]

        # Resolve status label.
        status = get_thread_status(thread_id)

        # Render a selectable inbox item.
        if st.sidebar.button(subject, key=f"inbox_btn_{thread_id}", width='stretch'):
            selected_thread_id = thread_id

        # Show status under the subject.
        st.sidebar.caption(f"Status: {status}")

        # Visually separate inbox items.
        st.sidebar.divider()

    # Return the selected thread id.
    return selected_thread_id


def render_thread(thread) -> None:
    """
    Render the selected email thread in the left column.
    """

    # Show the thread subject as a subheader.
    st.subheader(thread.subject)

    # Show a small thread summary line.
    st.caption(f"Thread ID: {thread.thread_id} · Messages: {len(thread.messages)}")

    # Render each message in the thread.
    for idx, msg in enumerate(thread.messages, start=1):
        # Create a container for a cleaner message layout.
        with st.container():
            # Show message heading.
            st.markdown(f"**Message {idx}**")

            # Show sender and timestamp.
            st.caption(f"From: {msg.from_} · Time: {msg.timestamp}")

            # Show message body.
            st.write(msg.body)

        # Visually separate messages.
        st.divider()


def render_result_overview(triage: dict | None, summary: dict | None, actions: list[dict]) -> None:
    """
    Render a compact overview of the main agent outputs.
    """

    # Resolve key triage fields safely.
    priority = triage.get("priority", "-") if triage else "-"
    category = triage.get("category", "-") if triage else "-"
    needs_reply = "Yes" if triage and triage.get("needs_reply") else "No"

    # Resolve summary ask safely.
    ask = summary.get("ask") if summary else None

    # Create overview KPI columns.
    col1, col2, col3, col4 = st.columns(4)

    # Show priority metric.
    col1.metric("Priority", priority)

    # Show category metric.
    col2.metric("Category", category)

    # Show reply requirement metric.
    col3.metric("Needs Reply", needs_reply)

    # Show number of proposed actions.
    col4.metric("Proposed Actions", len(actions))

    # Show the main ask when available.
    if ask:
        st.info(f"Main ask: {ask}")


def render_triage_summary_cards(triage: dict | None, summary: dict | None) -> None:
    """
    Render triage and summary in a more readable format.
    """

    # Render the triage section.
    with st.expander("Triage", expanded=True):
        # Handle missing triage.
        if not triage:
            st.info("No triage available.")
        else:
            # Show triage highlights.
            st.write(f"**Priority:** {triage.get('priority', '-')}")
            st.write(f"**Category:** {triage.get('category', '-')}")
            st.write(f"**Needs reply:** {'Yes' if triage.get('needs_reply') else 'No'}")
            st.write(f"**Rationale:** {triage.get('rationale', '-')}")

    # Render the summary section.
    with st.expander("Summary", expanded=True):
        # Handle missing summary.
        if not summary:
            st.info("No summary available.")
        else:
            # Resolve key points.
            key_points = summary.get("key_points", [])

            # Show summary bullets.
            if key_points:
                st.markdown("**Key points**")
                for point in key_points:
                    st.write(f"- {point}")
            else:
                st.write("No key points extracted.")

            # Show main ask when present.
            if summary.get("ask"):
                st.markdown(f"**Ask:** {summary['ask']}")


def render_actions(actions: list[dict], default_email_subject: str, default_email_body: str, thread_id: str) -> list[dict]:
    """
    Render the proposed actions as editable forms and collect approved actions.
    """

    # Initialize the list of edited and approved actions.
    approved_actions = []

    # Handle the empty actions case.
    if not actions:
        # Inform the user that no actions were proposed.
        st.info("No proposed actions.")

        # Return the empty approved actions list.
        return approved_actions

    # Render each proposed action one by one.
    for idx, action in enumerate(actions):
        # Show a title for the current action.
        st.markdown(f"### Action {idx + 1}")

        # Resolve the action type.
        action_type = action.get("type", "")

        # Resolve the action label.
        label = action.get("label", "")

        # Resolve whether approval is required.
        requires_approval = action.get("requires_approval", False)

        # Resolve the payload safely.
        payload = action.get("payload", {}) or {}

        # Show the action type.
        st.write(f"**Type:** {action_type}")

        # Show the action label.
        st.write(f"**Label:** {label}")

        # Show whether approval is required.
        st.write(f"**Requires approval:** {requires_approval}")

        # Build a thread-scoped widget key prefix.
        key_prefix = f"{thread_id}_action_{idx}"

        # Initialize the edited payload.
        edited_payload = {}

        # Render editable fields for send_email actions.
        if action_type == "send_email":
            # Resolve the initial recipient value.
            initial_recipient = payload.get("recipient", "")

            # Resolve the initial subject value.
            initial_subject = payload.get("subject", "") or default_email_subject

            # Resolve the initial body value.
            initial_body = payload.get("body", "") or default_email_body

            # Render the editable recipient field.
            edited_payload["recipient"] = st.text_input(
                "Recipient",
                value=initial_recipient,
                key=f"{key_prefix}_recipient",
            )

            # Render the editable subject field.
            edited_payload["subject"] = st.text_input(
                "Subject",
                value=initial_subject,
                key=f"{key_prefix}_subject",
            )

            # Render the editable body field.
            edited_payload["body"] = st.text_area(
                "Body",
                value=initial_body,
                height=180,
                key=f"{key_prefix}_body",
            )

        # Render editable fields for create_task actions.
        elif action_type == "create_task":
            # Render the editable task title field.
            edited_payload["title"] = st.text_input(
                "Title",
                value=payload.get("title", ""),
                key=f"{key_prefix}_title",
            )

            # Render the editable task description field.
            edited_payload["description"] = st.text_area(
                "Description",
                value=payload.get("description", ""),
                height=120,
                key=f"{key_prefix}_description",
            )

            # Render the editable due date field.
            edited_payload["due_date"] = st.text_input(
                "Due date",
                value=payload.get("due_date", ""),
                key=f"{key_prefix}_due_date",
            )

        # Render editable fields for create_calendar_event actions.
        elif action_type == "create_calendar_event":
            # Render the editable event title field.
            edited_payload["title"] = st.text_input(
                "Title",
                value=payload.get("title", ""),
                key=f"{key_prefix}_title",
            )

            # Render the editable event description field.
            edited_payload["description"] = st.text_area(
                "Description",
                value=payload.get("description", ""),
                height=120,
                key=f"{key_prefix}_description",
            )

            # Render the editable start time field.
            edited_payload["start_time"] = st.text_input(
                "Start time",
                value=payload.get("start_time", ""),
                key=f"{key_prefix}_start_time",
            )

            # Render the editable end time field.
            edited_payload["end_time"] = st.text_input(
                "End time",
                value=payload.get("end_time", ""),
                key=f"{key_prefix}_end_time",
            )

        # Render empty payload info for no-op actions.
        else:
            # Inform the user that this action has no editable payload.
            st.write("**Payload:** Empty")

        # Render a checkbox for approving this action.
        approved = st.checkbox(
            f"Approve action {idx + 1}",
            key=f"{key_prefix}_approved",
        )

        # Collect the edited action if approved.
        if approved:
            # Build the edited action object.
            approved_actions.append(
                {
                    "type": action_type,
                    "label": label,
                    "requires_approval": requires_approval,
                    "payload": edited_payload,
                }
            )

        # Visually separate actions.
        st.divider()

    # Return the edited and approved actions.
    return approved_actions


def render_execution_results(execution_results: list[dict]) -> None:
    """
    Render execution results in a more readable format.
    """

    # Show the execution section title.
    st.subheader("Execution Results")

    # Render each execution result as a compact block.
    for idx, item in enumerate(execution_results, start=1):
        # Resolve action type.
        action_type = item.get("action_type", "-")

        # Resolve label.
        label = item.get("label", "-")

        # Resolve result payload.
        result = item.get("result", {}) or {}

        # Resolve result status.
        status = result.get("status", "-")

        # Resolve result message.
        message = result.get("message", "-")

        # Render the result summary.
        st.markdown(f"**Result {idx}: {label}**")
        st.write(f"Type: {action_type}")
        st.write(f"Status: {status}")
        st.write(f"Message: {message}")

        # Show detailed record inside an expander.
        with st.expander(f"View record for result {idx}"):
            st.json(result.get("record", {}))

        # Visually separate result items.
        st.divider()


def render_metrics_table(metrics_dict: dict, empty_message: str) -> None:
    """
    Render a metrics dictionary as a Streamlit dataframe.
    """

    # Handle the empty metrics case.
    if not metrics_dict:
        # Inform the user that no metrics are available.
        st.info(empty_message)

        # Stop rendering the table.
        return

    # Initialize the table rows.
    rows = []

    # Convert the metrics dictionary into row records.
    for metric_name, metric_values in metrics_dict.items():
        # Build the row with metric name and values.
        row = {"name": metric_name}
        row.update(metric_values)

        # Append the row to the list.
        rows.append(row)

    # Convert the rows to a dataframe.
    df = pd.DataFrame(rows)

    # Render the dataframe in the UI.
    st.dataframe(df, width='stretch', hide_index=True)


def render_observability(metrics: dict) -> None:
    """
    Render combined observability metrics across the full page width.
    """

    # Show the section title.
    st.subheader("Observability")

    # Resolve top-level agent run metrics.
    agent_runs = metrics.get("agent_runs", {})

    # Resolve action metric summary.
    action_total, action_failures = get_action_metrics_summary(metrics)

    # Create KPI columns.
    kpi1, kpi2, kpi3, kpi4, kpi5 = st.columns(5)

    # Render total agent runs.
    kpi1.metric("Agent Runs", agent_runs.get("total", 0))

    # Render successful runs.
    kpi2.metric("Run Success", agent_runs.get("success", 0))

    # Render failed runs.
    kpi3.metric("Run Failed", agent_runs.get("failed", 0))

    # Render action execution count.
    kpi4.metric("Action Executions", action_total)

    # Render action failure count.
    kpi5.metric("Action Failures", action_failures)

    # Create metrics tabs for better readability.
    tab1, tab2 = st.tabs(["Node Metrics", "Action Metrics"])

    # Render node metrics.
    with tab1:
        render_metrics_table(
            metrics.get("nodes", {}),
            empty_message="No node metrics yet.",
        )

    # Render action execution metrics.
    with tab2:
        render_metrics_table(
            metrics.get("actions", {}),
            empty_message="No action metrics yet.",
        )


def refresh_metrics(agent_client: AgentApiClient, observability_placeholder) -> None:
    """
    Refresh cached observability metrics and update the top-level panel.
    """

    # Cache the latest combined metrics snapshot.
    st.session_state["observability_metrics"] = get_combined_metrics(agent_client)

    # Render the refreshed observability panel.
    with observability_placeholder.container():
        metrics = st.session_state.get("observability_metrics", {})
        if metrics:
            render_observability(metrics)


def main() -> None:
    """
    Define the Streamlit application entrypoint.
    """

    # Configure the page metadata.
    st.set_page_config(page_title="Email Agent", layout="wide")

    # Show the page title.
    st.title("Email Agent")

    # Create a placeholder for the top observability section.
    observability_placeholder = st.empty()

    # Create the mail store instance.
    store = MailStore()

    # Create the API client instance.
    agent_client = AgentApiClient()

    # Create the mock executor instance.
    executor = ActionExecutor()

    # Create the memory store instance.
    memory_store = MemoryStore()

    # Check whether the backend API is reachable.
    try:
        # Call the health endpoint.
        health = agent_client.health()

        # Show the backend status in the sidebar.
        st.sidebar.success(f"Agent API: {health['status']}")

        # Load combined observability metrics.
        st.session_state["observability_metrics"] = get_combined_metrics(agent_client)

    except Exception as exc:
        # Show the backend error in the sidebar.
        st.sidebar.error(f"Agent API unavailable: {exc}")

        # Stop rendering the rest of the UI.
        st.stop()

    # Render observability below the title across both columns.
    with observability_placeholder.container():
        metrics = st.session_state.get("observability_metrics", {})
        if metrics:
            render_observability(metrics)

    # Load available threads from the mock store.
    threads = store.list_threads()

    # Stop if no threads are available.
    if not threads:
        # Inform the user about the missing data.
        st.error("No threads found in data source.")

        # Stop further rendering.
        st.stop()

    # Initialize cached agent results per thread.
    if "agent_results" not in st.session_state:
        # Create the storage for agent results.
        st.session_state["agent_results"] = {}

    # Initialize cached execution results per thread.
    if "execution_results" not in st.session_state:
        # Create the storage for execution results.
        st.session_state["execution_results"] = {}

    # Initialize cached observability metrics.
    if "observability_metrics" not in st.session_state:
        # Create the storage for observability metrics.
        st.session_state["observability_metrics"] = {}

    # Render the inbox and resolve selected thread id.
    thread_id = render_inbox(threads)

    # Resolve the previously active thread id.
    previous_thread_id = st.session_state.get("active_thread_id")

    # Clear thread-scoped widget state when switching threads.
    if previous_thread_id and previous_thread_id != thread_id:
        # Resolve all thread-scoped widget keys to delete.
        keys_to_delete = [
            key
            for key in list(st.session_state.keys())
            if key.startswith(f"{previous_thread_id}_action_")
            or key.startswith(f"draft_subject_preview_{previous_thread_id}")
            or key.startswith(f"draft_body_preview_{previous_thread_id}")
        ]

        # Delete each stale widget key.
        for key in keys_to_delete:
            del st.session_state[key]

    # Persist the currently active thread id.
    st.session_state["active_thread_id"] = thread_id

    # Load the selected thread in validated form.
    thread = store.get_thread(thread_id)

    # Create the main page layout columns.
    col1, col2 = st.columns([2, 3])

    # Render the left column content.
    with col1:
        # Show the thread panel title.
        st.header("Thread")

        # Render the thread body.
        render_thread(thread)

        # Render the run button.
        run = st.button("Run Agent", type="primary", width='stretch')

    # Render the right column content.
    with col2:
        # Show the output panel title.
        st.header("Agent Output")

        # Run the agent when the button is pressed.
        if run:
            # Show a loading spinner while the agent runs.
            with st.spinner("Running agent..."):
                # Call the backend agent with the selected thread.
                result = agent_client.run(thread.model_dump(by_alias=True))

                # Cache the result under the selected thread id.
                st.session_state["agent_results"][thread_id] = result

                # Clear previous execution results for this thread.
                st.session_state["execution_results"][thread_id] = []

                # Refresh observability metrics after the run.
                refresh_metrics(agent_client, observability_placeholder)

        # Retrieve the cached result for the selected thread.
        result = st.session_state["agent_results"].get(thread_id)

        # Stop if the agent has not run yet.
        if not result:
            # Instruct the user how to proceed.
            st.info("Select a thread and click **Run Agent**.")

            # Stop further rendering.
            st.stop()

        # Extract the triage result.
        triage = result.get("triage")

        # Extract the summary result.
        summary = result.get("summary")

        # Extract the draft reply.
        draft = result.get("draft")

        # Extract the proposed actions.
        actions = result.get("proposed_actions", [])

        # Render the compact result overview.
        render_result_overview(triage, summary, actions)

        # Render readable triage and summary sections.
        render_triage_summary_cards(triage, summary)

        # Render the draft reply block.
        st.subheader("Draft Reply")

        # Resolve the draft subject safely.
        draft_subject = draft.get("subject", "") if draft else ""

        # Resolve the draft body safely.
        draft_body = draft.get("body", "") if draft else ""

        # Render the subject as read-only.
        st.text_input(
            "Subject",
            value=draft_subject,
            disabled=True,
            key=f"draft_subject_preview_{thread_id}",
        )

        # Render the draft body as a read-only preview.
        st.text_area(
            "Generated Draft Preview",
            value=draft_body,
            height=240,
            disabled=True,
            key=f"draft_body_preview_{thread_id}",
        )

        # Render the raw JSON details inside an expander.
        with st.expander("View raw agent response details", expanded=False):
            # Show raw triage payload.
            st.markdown("**Raw Triage**")
            st.json(triage)

            # Show raw summary payload.
            st.markdown("**Raw Summary**")
            st.json(summary)

        # Render the proposed actions section.
        st.subheader("Proposed Actions")

        # Render editable action cards and collect approved actions.
        approved_actions = render_actions(
            actions=actions,
            default_email_subject=draft_subject,
            default_email_body=draft_body,
            thread_id=thread_id,
        )

        # Render the human approval section.
        st.subheader("Human-in-the-loop")

        # Render the number of selected actions.
        st.caption(f"Selected actions: {len(approved_actions)}")

        # Render the button for executing selected actions.
        approve = st.button(
            "Approve selected actions",
            width='stretch',
            disabled=len(approved_actions) == 0,
        )

        # Execute the selected actions when approved.
        if approve:
            # Build the lightweight thread context for execution.
            thread_context = {
                "thread_id": thread.thread_id,
                "thread_subject": thread.subject,
            }

            # Execute all approved actions through the mock executor.
            execution_results = executor.execute_many(approved_actions, thread_context)

            # Persist memory updates derived from approved actions.
            memory_store.update_from_approved_actions(
                thread.thread_id,
                thread.subject,
                approved_actions,
            )

            # Cache execution results for this thread.
            st.session_state["execution_results"][thread_id] = execution_results

            # Refresh observability metrics after local action execution.
            refresh_metrics(agent_client, observability_placeholder)

            # Show a success message.
            st.success("Approved actions executed through mock adapters and memory updated.")

        # Retrieve the cached execution results for the selected thread.
        execution_results = st.session_state["execution_results"].get(thread_id, [])

        # Render execution results if any exist.
        if execution_results:
            render_execution_results(execution_results)


# Run the app only when executed directly.
if __name__ == "__main__":
    # Start the Streamlit app.
    main()