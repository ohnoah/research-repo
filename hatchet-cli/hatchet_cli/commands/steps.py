"""
Step Run Commands - Manage step runs in Hatchet.

Commands:
    get      - Get step run details
    logs     - Get step run logs
    events   - Get step run events
    archives - Get step run retry history
    schema   - Get step run input/output schema
    rerun    - Rerun a step
    cancel   - Cancel a step run
"""

from typing import Optional

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
    confirm,
    console,
)


@click.group()
def steps():
    """
    Manage step runs.

    Step runs are individual task executions within a workflow run.
    Use these commands to inspect logs, outputs, and manage step execution.

    Examples:

        # Get step details
        hatchet steps get <step-run-id>

        # View step logs
        hatchet steps logs <step-run-id>

        # Rerun a failed step
        hatchet steps rerun <step-run-id>
    """
    pass


@steps.command("get")
@click.argument("step_run_id")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def get_step_run(ctx, step_run_id: str, output_format: str):
    """
    Get step run details.

    Retrieves detailed information about a step run including its status,
    timing, input, output, and error information.

    STEP_RUN_ID is the step run UUID.

    Examples:

        # Get step details
        hatchet steps get abc123-def456-...

        # Get as JSON
        hatchet steps get abc123-def456-... --format json
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        step_run = client.get_step_run(step_run_id)

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            fields = [
                ("metadata.id", "ID"),
                ("step.readableId", "Step Name"),
                ("status", "Status", lambda x: str(colorize_status(x)) if x else "-"),
                ("metadata.createdAt", "Created", lambda x: format_timestamp(x)),
                ("startedAt", "Started", lambda x: format_timestamp(x) if x else "-"),
                ("finishedAt", "Finished", lambda x: format_timestamp(x) if x else "-"),
                ("startedAt", "Duration", lambda _: format_duration(step_run.get("startedAt"), step_run.get("finishedAt"))),
                ("retryCount", "Retries", lambda x: str(x) if x is not None else "0"),
            ]
            output_detail(step_run, fields, title="Step Run")

            # Show input
            input_data = step_run.get("input")
            if input_data:
                click.echo("\nInput:")
                output_json(input_data)

            # Show output
            output_data = step_run.get("output")
            if output_data:
                click.echo("\nOutput:")
                output_json(output_data)

            # Show error if present
            error = step_run.get("error")
            if error:
                click.echo(f"\n[red]Error:[/red] {error}")

            # Show cancellation info
            cancel_reason = step_run.get("cancelledReason")
            if cancel_reason:
                click.echo(f"\nCancellation Reason: {cancel_reason}")

        else:
            formatter.output(step_run)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@steps.command("logs")
@click.argument("step_run_id")
@click.option("--limit", "-l", default=100, help="Maximum number of log entries")
@click.option("--offset", default=0, help="Pagination offset")
@click.option("--follow", "-F", is_flag=True, help="Follow logs (not yet implemented)")
@click.option("--format", "-f", "output_format", type=click.Choice(["text", "json", "yaml"]), default="text", help="Output format")
@click.pass_context
def step_run_logs(
    ctx,
    step_run_id: str,
    limit: int,
    offset: int,
    follow: bool,
    output_format: str,
):
    """
    Get step run logs.

    Retrieves log output from a step run execution.

    STEP_RUN_ID is the step run UUID.

    Examples:

        # Get logs
        hatchet steps logs abc123-def456-...

        # Get last 50 log entries
        hatchet steps logs abc123-def456-... --limit 50

        # Get logs as JSON
        hatchet steps logs abc123-def456-... --format json
    """
    try:
        if follow:
            click.echo("Note: --follow is not yet implemented. Showing current logs.")

        client: HatchetClient = ctx.obj["client"]
        result = client.get_step_run_logs(step_run_id, offset=offset, limit=limit)

        logs = result.get("rows", result) if isinstance(result, dict) else result

        if not logs:
            click.echo("No logs found for this step run.")
            return

        if output_format == "text":
            for log_entry in logs if isinstance(logs, list) else [logs]:
                if isinstance(log_entry, dict):
                    timestamp = format_timestamp(log_entry.get("createdAt", ""))
                    level = log_entry.get("level", "INFO")
                    message = log_entry.get("message", log_entry.get("line", ""))

                    # Color code log level
                    level_colors = {
                        "DEBUG": "dim",
                        "INFO": "blue",
                        "WARN": "yellow",
                        "WARNING": "yellow",
                        "ERROR": "red",
                        "FATAL": "red bold",
                    }
                    level_color = level_colors.get(level.upper(), "white")

                    console.print(f"[dim]{timestamp}[/dim] [{level_color}]{level}[/{level_color}] {message}")
                else:
                    click.echo(log_entry)
        else:
            formatter = OutputFormatter(output_format)
            formatter.output(logs)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@steps.command("events")
@click.argument("step_run_id")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def step_run_events(ctx, step_run_id: str, output_format: str):
    """
    Get step run events.

    Shows the timeline of events for a step run including state changes,
    retries, and completion.

    STEP_RUN_ID is the step run UUID.

    Examples:

        hatchet steps events abc123-def456-...
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.get_step_run_events(step_run_id)

        events = result.get("rows", result) if isinstance(result, dict) else result

        if not events:
            click.echo("No events found for this step run.")
            return

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            if isinstance(events, list):
                columns = [
                    ("reason", "Reason"),
                    ("severity", "Severity"),
                    ("message", "Message"),
                    ("timeFirstSeen", "Time", lambda x: format_timestamp(x)),
                ]
                output_table(events, columns, title="Step Run Events")
            else:
                output_json(events)
        else:
            formatter.output(events)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@steps.command("archives")
@click.argument("step_run_id")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def step_run_archives(ctx, step_run_id: str, output_format: str):
    """
    Get step run retry history.

    Shows the history of retry attempts for a step run, including
    previous inputs, outputs, and errors.

    STEP_RUN_ID is the step run UUID.

    Examples:

        hatchet steps archives abc123-def456-...
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.get_step_run_archives(step_run_id)

        archives = result.get("rows", result) if isinstance(result, dict) else result

        if not archives:
            click.echo("No archives found for this step run.")
            return

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            if isinstance(archives, list):
                columns = [
                    ("retryCount", "Retry #"),
                    ("status", "Status", lambda x: str(colorize_status(x)) if x else "-"),
                    ("startedAt", "Started", lambda x: format_timestamp(x) if x else "-"),
                    ("finishedAt", "Finished", lambda x: format_timestamp(x) if x else "-"),
                    ("error", "Error", lambda x: (x[:50] + "...") if x and len(x) > 50 else (x or "-")),
                ]
                output_table(archives, columns, title="Step Run Archives")
            else:
                output_json(archives)
        else:
            formatter.output(archives)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@steps.command("schema")
@click.argument("step_run_id")
@click.option("--format", "-f", "output_format", type=click.Choice(["json", "yaml"]), default="json", help="Output format")
@click.pass_context
def step_run_schema(ctx, step_run_id: str, output_format: str):
    """
    Get step run input/output schema.

    Shows the JSON schema for the step's expected input and output.

    STEP_RUN_ID is the step run UUID.

    Examples:

        hatchet steps schema abc123-def456-...
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.get_step_run_schema(step_run_id)

        formatter = OutputFormatter(output_format)
        formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@steps.command("rerun")
@click.argument("step_run_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def rerun_step(ctx, step_run_id: str, yes: bool, output_format: str):
    """
    Rerun a step.

    Creates a new attempt of the step using the same input.
    Useful for retrying failed steps.

    STEP_RUN_ID is the step run UUID.

    Examples:

        # Rerun with confirmation
        hatchet steps rerun abc123-def456-...

        # Rerun without confirmation
        hatchet steps rerun abc123-def456-... --yes
    """
    try:
        if not yes:
            if not confirm("Are you sure you want to rerun this step?"):
                click.echo("Cancelled.")
                return

        client: HatchetClient = ctx.obj["client"]
        result = client.rerun_step(step_run_id)

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            output_success("Step rerun initiated.")
            if isinstance(result, dict):
                new_id = result.get("id", result.get("stepRunId"))
                if new_id:
                    click.echo(f"New Step Run ID: {new_id}")
        else:
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@steps.command("cancel")
@click.argument("step_run_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def cancel_step(ctx, step_run_id: str, yes: bool):
    """
    Cancel a step run.

    Stops a running step. Steps that have already completed
    cannot be cancelled.

    STEP_RUN_ID is the step run UUID.

    Examples:

        # Cancel with confirmation
        hatchet steps cancel abc123-def456-...

        # Cancel without confirmation
        hatchet steps cancel abc123-def456-... --yes
    """
    try:
        if not yes:
            if not confirm("Are you sure you want to cancel this step run?"):
                click.echo("Cancelled.")
                return

        client: HatchetClient = ctx.obj["client"]
        client.cancel_step_run(step_run_id)
        output_success("Step run cancelled.")

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)
