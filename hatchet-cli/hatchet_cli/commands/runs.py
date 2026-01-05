"""
Workflow Run Commands - Manage workflow runs in Hatchet.

Commands:
    list    - List workflow runs with filtering
    get     - Get workflow run details
    status  - Get workflow run status
    input   - Get workflow run input data
    cancel  - Cancel workflow run(s)
    replay  - Replay workflow run(s)
    metrics - Get workflow run metrics
    events  - Get task events for a run
    shape   - Get DAG shape of a run
"""

import json
from typing import List, Optional

import click

from ..client import HatchetClient
from ..exceptions import HatchetAPIError, HatchetConfigurationError
from ..output import (
    OutputFormatter,
    colorize_status,
    format_duration,
    format_timestamp,
    output_error,
    output_success,
    output_table,
    output_detail,
    output_json,
    output_tree,
    confirm,
)


VALID_STATUSES = ["PENDING", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED"]
VALID_KINDS = ["DEFAULT", "SCHEDULED", "CRON", "CHILD", "EVENT"]


@click.group()
def runs():
    """
    Manage workflow runs.

    Workflow runs are instances of workflow executions. Use these commands
    to list, inspect, cancel, and replay runs.

    Examples:

        # List all runs
        hatchet runs list

        # List failed runs
        hatchet runs list --status FAILED

        # Get run details
        hatchet runs get <run-id>

        # Cancel a run
        hatchet runs cancel <run-id>

        # Replay failed runs
        hatchet runs replay <run-id>
    """
    pass


@runs.command("list")
@click.option("--workflow", "-w", help="Filter by workflow ID or name")
@click.option("--status", "-s", multiple=True, type=click.Choice(VALID_STATUSES), help="Filter by status (can specify multiple)")
@click.option("--kind", "-k", multiple=True, type=click.Choice(VALID_KINDS), help="Filter by run kind")
@click.option("--event-id", help="Filter by triggering event ID")
@click.option("--parent-run", help="Filter by parent workflow run ID")
@click.option("--metadata", "-m", multiple=True, help="Filter by metadata (key:value format)")
@click.option("--created-after", help="Filter runs created after (ISO 8601)")
@click.option("--created-before", help="Filter runs created before (ISO 8601)")
@click.option("--finished-after", help="Filter runs finished after (ISO 8601)")
@click.option("--finished-before", help="Filter runs finished before (ISO 8601)")
@click.option("--order-by", type=click.Choice(["createdAt", "finishedAt"]), default="createdAt", help="Field to order by")
@click.option("--order", type=click.Choice(["ASC", "DESC"]), default="DESC", help="Order direction")
@click.option("--limit", "-l", default=20, help="Maximum number of runs to return")
@click.option("--offset", default=0, help="Pagination offset")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def list_runs(
    ctx,
    workflow: Optional[str],
    status: tuple,
    kind: tuple,
    event_id: Optional[str],
    parent_run: Optional[str],
    metadata: tuple,
    created_after: Optional[str],
    created_before: Optional[str],
    finished_after: Optional[str],
    finished_before: Optional[str],
    order_by: str,
    order: str,
    limit: int,
    offset: int,
    output_format: str,
):
    """
    List workflow runs with filtering.

    Shows workflow runs with various filtering options. Results are
    paginated and can be sorted by creation or completion time.

    Examples:

        # List all runs
        hatchet runs list

        # List only failed runs
        hatchet runs list --status FAILED

        # List runs for a specific workflow
        hatchet runs list --workflow my-workflow

        # List runs with multiple status filters
        hatchet runs list --status RUNNING --status PENDING

        # List runs from the last hour
        hatchet runs list --created-after 2024-01-15T10:00:00Z

        # List runs with specific metadata
        hatchet runs list --metadata env:production

        # Paginate through results
        hatchet runs list --limit 20 --offset 40
    """
    try:
        client: HatchetClient = ctx.obj["client"]

        # Convert metadata to list format
        metadata_list = list(metadata) if metadata else None

        result = client.list_workflow_runs(
            workflow_id=workflow,
            statuses=list(status) if status else None,
            kinds=list(kind) if kind else None,
            event_id=event_id,
            parent_workflow_run_id=parent_run,
            additional_metadata=metadata_list,
            created_after=created_after,
            created_before=created_before,
            finished_after=finished_after,
            finished_before=finished_before,
            order_by_field=order_by,
            order_by_direction=order,
            limit=limit,
            offset=offset,
        )

        runs_list = result.get("rows", [])
        pagination = result.get("pagination", {})

        if not runs_list:
            click.echo("No workflow runs found.")
            return

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            columns = [
                ("metadata.id", "ID", lambda x: x[:12] + "..." if x else "-"),
                ("workflowVersion.workflow.name", "Workflow"),
                ("status", "Status", lambda x: str(colorize_status(x)) if x else "-"),
                ("metadata.createdAt", "Created", lambda x: format_timestamp(x, relative=True)),
                ("startedAt", "Started", lambda x: format_timestamp(x, relative=True) if x else "-"),
                ("finishedAt", "Finished", lambda x: format_timestamp(x, relative=True) if x else "-"),
            ]

            total = pagination.get("num_pages", 0) * limit
            current_page = (offset // limit) + 1
            output_table(runs_list, columns, title=f"Workflow Runs (showing {len(runs_list)}, page {current_page})")

            if len(runs_list) >= limit:
                click.echo(f"\nTip: Use --offset {offset + limit} to see more results")
        else:
            formatter.output(runs_list)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@runs.command("get")
@click.argument("run_id")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def get_run(ctx, run_id: str, output_format: str):
    """
    Get workflow run details.

    Retrieves comprehensive information about a workflow run including
    its status, timing, steps, and output.

    RUN_ID is the workflow run UUID.

    Examples:

        # Get run details
        hatchet runs get abc123-def456-...

        # Get as JSON
        hatchet runs get abc123-def456-... --format json
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        run = client.get_workflow_run(run_id)

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            fields = [
                ("metadata.id", "ID"),
                ("displayName", "Display Name"),
                ("workflowVersion.workflow.name", "Workflow"),
                ("workflowVersion.version", "Version"),
                ("status", "Status", lambda x: str(colorize_status(x)) if x else "-"),
                ("metadata.createdAt", "Created", lambda x: format_timestamp(x)),
                ("startedAt", "Started", lambda x: format_timestamp(x) if x else "-"),
                ("finishedAt", "Finished", lambda x: format_timestamp(x) if x else "-"),
                ("startedAt", "Duration", lambda _: format_duration(run.get("startedAt"), run.get("finishedAt"))),
            ]
            output_detail(run, fields, title=f"Workflow Run")

            # Show triggered by info
            triggered_by = run.get("triggeredBy")
            if triggered_by:
                click.echo("\nTriggered By:")
                if triggered_by.get("event"):
                    click.echo(f"  Event: {triggered_by['event'].get('key', 'unknown')}")
                elif triggered_by.get("cron"):
                    click.echo(f"  Cron: {triggered_by['cron']}")
                elif triggered_by.get("parent"):
                    click.echo(f"  Parent Run: {triggered_by['parent'].get('id', 'unknown')}")

            # Show job runs
            job_runs = run.get("jobRuns", [])
            if job_runs:
                click.echo("\nJob Runs:")
                for job_run in job_runs:
                    job_name = job_run.get("job", {}).get("name", "unnamed")
                    status = job_run.get("status", "UNKNOWN")
                    click.echo(f"  [{colorize_status(status)}] {job_name}")

                    step_runs = job_run.get("stepRuns", [])
                    for step_run in step_runs:
                        step_name = step_run.get("step", {}).get("readableId", step_run.get("id", "unnamed"))
                        step_status = step_run.get("status", "UNKNOWN")
                        click.echo(f"    - [{colorize_status(step_status)}] {step_name}")

            # Show error if failed
            if run.get("error"):
                click.echo(f"\nError: {run.get('error')}")
        else:
            formatter.output(run)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@runs.command("status")
@click.argument("run_id")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def run_status(ctx, run_id: str, output_format: str):
    """
    Get workflow run status.

    Quick status check for a workflow run.

    RUN_ID is the workflow run UUID.

    Examples:

        hatchet runs status abc123-def456-...
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.get_workflow_run_status(run_id)

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            status = result.get("status", "UNKNOWN")
            click.echo(f"Status: {colorize_status(status)}")
        else:
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@runs.command("inspect")
@click.argument("run_id")
@click.option("--show-input", "-i", is_flag=True, help="Show workflow input data")
@click.option("--show-output", "-o", is_flag=True, help="Show task outputs")
@click.option("--show-children", "-c", is_flag=True, help="Show child workflow runs")
@click.option("--show-all", "-a", is_flag=True, help="Show all details (input, output, children)")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def inspect_run(
    ctx,
    run_id: str,
    show_input: bool,
    show_output: bool,
    show_children: bool,
    show_all: bool,
    output_format: str,
):
    """
    Deep inspection of a workflow run.

    Provides comprehensive details about a workflow run including:
    - Run status and timing
    - Task/step execution details with timing
    - Input data (with --show-input or --show-all)
    - Task outputs (with --show-output or --show-all)
    - Child workflow runs (with --show-children or --show-all)

    This is the go-to command for investigating workflow executions.

    RUN_ID is the workflow run UUID.

    Examples:

        # Basic inspection
        hatchet runs inspect abc123-def456-...

        # Full inspection with all details
        hatchet runs inspect abc123-def456-... --show-all

        # Just show outputs
        hatchet runs inspect abc123-def456-... --show-output

        # Inspect with JSON output for scripting
        hatchet runs inspect abc123-def456-... -a --format json
    """
    try:
        client: HatchetClient = ctx.obj["client"]

        if show_all:
            show_input = show_output = show_children = True

        # Get the main run data
        run = client.get_workflow_run(run_id)

        if output_format != "table":
            # For JSON/YAML, collect all data into one object
            result = {"run": run}

            if show_input:
                try:
                    result["input"] = client.get_workflow_run_input(run_id)
                except Exception:
                    result["input"] = None

            if show_children:
                try:
                    children = client.list_child_runs(run_id)
                    result["children"] = children.get("rows", [])
                except Exception:
                    result["children"] = []

            try:
                result["timings"] = client.get_task_timings(run_id)
            except Exception:
                result["timings"] = None

            formatter = OutputFormatter(output_format)
            formatter.output(result)
            return

        # Table format - rich display
        from rich.console import Console
        from rich.panel import Panel
        from rich.table import Table
        from rich import box

        console = Console()

        # === Header ===
        workflow_name = run.get("workflowVersion", {}).get("workflow", {}).get("name", "Unknown")
        status = run.get("status", "UNKNOWN")
        console.print(Panel(
            f"[bold]{workflow_name}[/bold]\n"
            f"Run ID: {run_id}\n"
            f"Status: {colorize_status(status)}",
            title="Workflow Run",
            expand=False,
        ))

        # === Timing ===
        console.print("\n[bold]Timing[/bold]")
        created = format_timestamp(run.get("metadata", {}).get("createdAt"))
        started = format_timestamp(run.get("startedAt")) if run.get("startedAt") else "-"
        finished = format_timestamp(run.get("finishedAt")) if run.get("finishedAt") else "-"
        duration = format_duration(run.get("startedAt"), run.get("finishedAt"))
        console.print(f"  Created:  {created}")
        console.print(f"  Started:  {started}")
        console.print(f"  Finished: {finished}")
        console.print(f"  Duration: {duration}")

        # === Input ===
        if show_input:
            console.print("\n[bold]Input Data[/bold]")
            try:
                input_data = client.get_workflow_run_input(run_id)
                if input_data:
                    output_json(input_data)
                else:
                    console.print("  [dim]No input data[/dim]")
            except Exception as e:
                console.print(f"  [dim]Could not fetch input: {e}[/dim]")

        # === Tasks/Steps ===
        console.print("\n[bold]Tasks[/bold]")

        # Try to get timing info for more detail
        try:
            timings = client.get_task_timings(run_id)
            timing_data = timings if isinstance(timings, list) else timings.get("rows", [])
        except Exception:
            timing_data = []

        job_runs = run.get("jobRuns", [])
        if job_runs:
            task_table = Table(box=box.SIMPLE)
            task_table.add_column("Task", style="bold")
            task_table.add_column("Status")
            task_table.add_column("Duration")
            task_table.add_column("Started")

            for job_run in job_runs:
                step_runs = job_run.get("stepRuns", [])
                for step_run in step_runs:
                    step_name = step_run.get("step", {}).get("readableId", step_run.get("id", "unnamed")[:12])
                    step_status = step_run.get("status", "UNKNOWN")
                    step_started = format_timestamp(step_run.get("startedAt"), relative=True) if step_run.get("startedAt") else "-"
                    step_duration = format_duration(step_run.get("startedAt"), step_run.get("finishedAt"))

                    task_table.add_row(
                        step_name,
                        str(colorize_status(step_status)),
                        step_duration,
                        step_started,
                    )

                    # Show output if requested
                    if show_output and step_run.get("output"):
                        console.print(task_table)
                        console.print(f"\n  [dim]Output for {step_name}:[/dim]")
                        output_json(step_run.get("output"))
                        task_table = Table(box=box.SIMPLE)
                        task_table.add_column("Task", style="bold")
                        task_table.add_column("Status")
                        task_table.add_column("Duration")
                        task_table.add_column("Started")

            if task_table.row_count > 0:
                console.print(task_table)
        else:
            console.print("  [dim]No tasks found[/dim]")

        # === Errors ===
        error = run.get("error")
        if error:
            console.print(f"\n[bold red]Error[/bold red]")
            console.print(f"  {error}")

        # === Child Runs ===
        if show_children:
            console.print("\n[bold]Child Workflow Runs[/bold]")
            try:
                children = client.list_child_runs(run_id)
                child_runs = children.get("rows", [])
                if child_runs:
                    child_table = Table(box=box.SIMPLE)
                    child_table.add_column("ID")
                    child_table.add_column("Workflow")
                    child_table.add_column("Status")
                    child_table.add_column("Duration")

                    for child in child_runs:
                        child_id = child.get("metadata", {}).get("id", "")[:12] + "..."
                        child_workflow = child.get("workflowVersion", {}).get("workflow", {}).get("name", "unknown")
                        child_status = child.get("status", "UNKNOWN")
                        child_duration = format_duration(child.get("startedAt"), child.get("finishedAt"))
                        child_table.add_row(
                            child_id,
                            child_workflow,
                            str(colorize_status(child_status)),
                            child_duration,
                        )

                    console.print(child_table)
                    console.print(f"\n  [dim]Tip: Inspect a child with: hatchet runs inspect <child-id>[/dim]")
                else:
                    console.print("  [dim]No child runs[/dim]")
            except Exception as e:
                console.print(f"  [dim]Could not fetch child runs: {e}[/dim]")

        # === Triggered By ===
        triggered_by = run.get("triggeredBy")
        if triggered_by:
            console.print("\n[bold]Triggered By[/bold]")
            if triggered_by.get("event"):
                console.print(f"  Event: {triggered_by['event'].get('key', 'unknown')}")
            elif triggered_by.get("cron"):
                console.print(f"  Cron: {triggered_by['cron']}")
            elif triggered_by.get("parent"):
                parent_id = triggered_by['parent'].get('id', 'unknown')
                console.print(f"  Parent Run: {parent_id}")
                console.print(f"  [dim]Tip: Inspect parent with: hatchet runs inspect {parent_id}[/dim]")

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@runs.command("children")
@click.argument("run_id")
@click.option("--limit", "-l", default=20, help="Maximum number of children to return")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def list_children(ctx, run_id: str, limit: int, output_format: str):
    """
    List child workflow runs.

    Shows all child workflows spawned by the specified parent run.

    RUN_ID is the parent workflow run UUID.

    Examples:

        hatchet runs children abc123-def456-...
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.list_child_runs(run_id, limit=limit)

        child_runs = result.get("rows", [])

        if not child_runs:
            click.echo("No child workflow runs found.")
            return

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            columns = [
                ("metadata.id", "ID", lambda x: x[:12] + "..." if x else "-"),
                ("workflowVersion.workflow.name", "Workflow"),
                ("status", "Status", lambda x: str(colorize_status(x)) if x else "-"),
                ("metadata.createdAt", "Created", lambda x: format_timestamp(x, relative=True)),
                ("finishedAt", "Duration", lambda _: "-"),  # Will be calculated
            ]

            # Add duration calculation
            for child in child_runs:
                child["_duration"] = format_duration(child.get("startedAt"), child.get("finishedAt"))

            columns[4] = ("_duration", "Duration")
            output_table(child_runs, columns, title=f"Child Runs of {run_id[:12]}... ({len(child_runs)} total)")
        else:
            formatter.output(child_runs)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@runs.command("timings")
@click.argument("run_id")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def run_timings(ctx, run_id: str, output_format: str):
    """
    Get detailed task timing information.

    Shows execution timing for each task in the workflow run.

    RUN_ID is the workflow run UUID.

    Examples:

        hatchet runs timings abc123-def456-...
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.get_task_timings(run_id)

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            timings = result if isinstance(result, list) else result.get("rows", result)
            if timings and isinstance(timings, list):
                columns = [
                    ("stepName", "Task"),
                    ("status", "Status", lambda x: str(colorize_status(x)) if x else "-"),
                    ("startedAt", "Started", lambda x: format_timestamp(x) if x else "-"),
                    ("finishedAt", "Finished", lambda x: format_timestamp(x) if x else "-"),
                ]
                output_table(timings, columns, title="Task Timings")
            else:
                output_json(result)
        else:
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@runs.command("input")
@click.argument("run_id")
@click.option("--format", "-f", "output_format", type=click.Choice(["json", "yaml"]), default="json", help="Output format")
@click.pass_context
def run_input(ctx, run_id: str, output_format: str):
    """
    Get workflow run input data.

    Shows the input data that was passed when the workflow run was triggered.

    RUN_ID is the workflow run UUID.

    Examples:

        hatchet runs input abc123-def456-...
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.get_workflow_run_input(run_id)

        formatter = OutputFormatter(output_format)
        formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@runs.command("shape")
@click.argument("run_id")
@click.option("--format", "-f", "output_format", type=click.Choice(["tree", "json", "yaml"]), default="tree", help="Output format")
@click.pass_context
def run_shape(ctx, run_id: str, output_format: str):
    """
    Get the DAG shape of a workflow run.

    Shows the structure of the workflow run including all jobs and steps
    and their dependencies.

    RUN_ID is the workflow run UUID.

    Examples:

        hatchet runs shape abc123-def456-...
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.get_workflow_run_shape(run_id)

        if output_format == "tree":
            output_tree(result, title=f"Workflow Run Shape: {run_id[:12]}...")
        else:
            formatter = OutputFormatter(output_format)
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@runs.command("events")
@click.argument("run_id")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def run_events(ctx, run_id: str, output_format: str):
    """
    Get task events for a workflow run.

    Shows the timeline of events that occurred during the workflow run.

    RUN_ID is the workflow run UUID.

    Examples:

        hatchet runs events abc123-def456-...
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.get_task_events(run_id)

        events_list = result.get("rows", result) if isinstance(result, dict) else result

        if not events_list:
            click.echo("No events found for this run.")
            return

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            if isinstance(events_list, list):
                columns = [
                    ("eventType", "Event Type"),
                    ("message", "Message"),
                    ("timestamp", "Timestamp", lambda x: format_timestamp(x)),
                ]
                output_table(events_list, columns, title="Task Events")
            else:
                output_json(events_list)
        else:
            formatter.output(events_list)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@runs.command("cancel")
@click.argument("run_ids", nargs=-1, required=True)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def cancel_runs(ctx, run_ids: tuple, yes: bool):
    """
    Cancel one or more workflow runs.

    Stops running workflow runs. Runs that have already completed
    cannot be cancelled.

    RUN_IDS are the workflow run UUIDs to cancel (space-separated).

    Examples:

        # Cancel a single run
        hatchet runs cancel abc123-def456-...

        # Cancel multiple runs
        hatchet runs cancel run1-id run2-id run3-id

        # Cancel without confirmation
        hatchet runs cancel abc123-def456-... --yes
    """
    try:
        if not yes:
            if not confirm(f"Are you sure you want to cancel {len(run_ids)} run(s)?"):
                click.echo("Cancelled.")
                return

        client: HatchetClient = ctx.obj["client"]
        result = client.cancel_workflow_runs(list(run_ids))
        output_success(f"Cancelled {len(run_ids)} workflow run(s).")

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@runs.command("replay")
@click.argument("run_ids", nargs=-1, required=True)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def replay_runs(ctx, run_ids: tuple, yes: bool, output_format: str):
    """
    Replay one or more workflow runs.

    Creates new workflow runs with the same input as the original runs.
    Useful for retrying failed runs.

    RUN_IDS are the workflow run UUIDs to replay (space-separated).

    Examples:

        # Replay a single run
        hatchet runs replay abc123-def456-...

        # Replay multiple runs
        hatchet runs replay run1-id run2-id run3-id

        # Replay without confirmation
        hatchet runs replay abc123-def456-... --yes
    """
    try:
        if not yes:
            if not confirm(f"Are you sure you want to replay {len(run_ids)} run(s)?"):
                click.echo("Cancelled.")
                return

        client: HatchetClient = ctx.obj["client"]
        result = client.replay_workflow_runs(list(run_ids))

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            output_success(f"Replayed {len(run_ids)} workflow run(s).")
            new_runs = result.get("workflowRuns", [])
            if new_runs:
                click.echo("New run IDs:")
                for run in new_runs:
                    run_id = run.get("id", run.get("workflowRunId", "unknown"))
                    click.echo(f"  - {run_id}")
        else:
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@runs.command("metrics")
@click.option("--workflow", "-w", help="Filter by workflow ID")
@click.option("--parent-run", help="Filter by parent workflow run ID")
@click.option("--event-id", help="Filter by event ID")
@click.option("--metadata", "-m", multiple=True, help="Filter by metadata (key:value format)")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def runs_metrics(
    ctx,
    workflow: Optional[str],
    parent_run: Optional[str],
    event_id: Optional[str],
    metadata: tuple,
    output_format: str,
):
    """
    Get aggregated workflow run metrics.

    Shows counts of runs by status and other aggregate statistics.

    Examples:

        # Get all metrics
        hatchet runs metrics

        # Get metrics for a specific workflow
        hatchet runs metrics --workflow my-workflow
    """
    try:
        client: HatchetClient = ctx.obj["client"]

        metadata_list = list(metadata) if metadata else None

        result = client.get_workflow_run_metrics(
            workflow_id=workflow,
            parent_workflow_run_id=parent_run,
            event_id=event_id,
            additional_metadata=metadata_list,
        )

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            click.echo("Workflow Run Metrics")
            click.echo("=" * 40)

            counts = result.get("counts", result)
            if isinstance(counts, list):
                for item in counts:
                    status = item.get("status", "UNKNOWN")
                    count = item.get("count", 0)
                    click.echo(f"  {colorize_status(status)}: {count}")
            elif isinstance(counts, dict):
                for status, count in counts.items():
                    click.echo(f"  {colorize_status(status)}: {count}")
            else:
                output_json(result)
        else:
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)
