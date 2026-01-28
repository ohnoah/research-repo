"""
Scheduled Run Commands - Manage scheduled workflow runs in Hatchet.

Commands:
    list   - List scheduled runs
    get    - Get scheduled run details
    create - Schedule a workflow run
    delete - Delete a scheduled run
"""

import json
from datetime import datetime, timedelta
from typing import Optional

import click
from dateutil import parser as dateparser

from ..client import HatchetClient
from ..exceptions import HatchetAPIError, HatchetConfigurationError
from ..output import (
    OutputFormatter,
    format_timestamp,
    output_error,
    output_success,
    output_table,
    output_detail,
    output_json,
    confirm,
)


def parse_time_spec(time_spec: str) -> str:
    """
    Parse a time specification into ISO 8601 format.

    Supports:
    - ISO 8601 timestamps: 2024-01-15T10:00:00Z
    - Relative times: +1h, +30m, +1d, +1w
    """
    if time_spec.startswith("+"):
        # Relative time
        amount = int(time_spec[1:-1])
        unit = time_spec[-1].lower()

        now = datetime.utcnow()

        if unit == "m":
            delta = timedelta(minutes=amount)
        elif unit == "h":
            delta = timedelta(hours=amount)
        elif unit == "d":
            delta = timedelta(days=amount)
        elif unit == "w":
            delta = timedelta(weeks=amount)
        else:
            raise ValueError(f"Unknown time unit: {unit}")

        target = now + delta
        return target.strftime("%Y-%m-%dT%H:%M:%SZ")
    else:
        # Try to parse as ISO 8601
        dt = dateparser.parse(time_spec)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


@click.group()
def scheduled():
    """
    Manage scheduled workflow runs.

    Scheduled runs are workflow executions set to trigger at a specific time.
    Use these commands to schedule, list, and manage future runs.

    Examples:

        # List scheduled runs
        hatchet scheduled list

        # Schedule a run
        hatchet scheduled create my-workflow --at "2024-01-15T10:00:00Z"

        # Delete a scheduled run
        hatchet scheduled delete <scheduled-id>
    """
    pass


@scheduled.command("list")
@click.option("--workflow", "-w", help="Filter by workflow ID")
@click.option("--metadata", "-m", multiple=True, help="Filter by metadata (key:value format)")
@click.option("--order-by", type=click.Choice(["createdAt", "triggerAt"]), default="triggerAt", help="Field to order by")
@click.option("--order", type=click.Choice(["ASC", "DESC"]), default="ASC", help="Order direction")
@click.option("--limit", "-l", default=20, help="Maximum number to return")
@click.option("--offset", default=0, help="Pagination offset")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def list_scheduled(
    ctx,
    workflow: Optional[str],
    metadata: tuple,
    order_by: str,
    order: str,
    limit: int,
    offset: int,
    output_format: str,
):
    """
    List scheduled workflow runs.

    Shows all pending scheduled runs that haven't been triggered yet.

    Examples:

        # List all scheduled runs
        hatchet scheduled list

        # Filter by workflow
        hatchet scheduled list --workflow my-workflow

        # Order by trigger time (ascending - soonest first)
        hatchet scheduled list --order-by triggerAt --order ASC
    """
    try:
        client: HatchetClient = ctx.obj["client"]

        metadata_list = list(metadata) if metadata else None

        result = client.list_scheduled_runs(
            workflow_id=workflow,
            additional_metadata=metadata_list,
            order_by_field=order_by,
            order_by_direction=order,
            limit=limit,
            offset=offset,
        )

        scheduled_list = result.get("rows", [])

        if not scheduled_list:
            click.echo("No scheduled runs found.")
            return

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            columns = [
                ("metadata.id", "ID", lambda x: x[:12] + "..." if x else "-"),
                ("workflowVersion.workflow.name", "Workflow"),
                ("triggerAt", "Trigger At", lambda x: format_timestamp(x)),
                ("metadata.createdAt", "Created", lambda x: format_timestamp(x, relative=True)),
            ]
            output_table(scheduled_list, columns, title=f"Scheduled Runs ({len(scheduled_list)})")
        else:
            formatter.output(scheduled_list)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@scheduled.command("get")
@click.argument("scheduled_id")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def get_scheduled(ctx, scheduled_id: str, output_format: str):
    """
    Get scheduled run details.

    Retrieves detailed information about a scheduled run.

    SCHEDULED_ID is the scheduled run UUID.

    Examples:

        hatchet scheduled get abc123-def456-...
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        scheduled = client.get_scheduled_run(scheduled_id)

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            fields = [
                ("metadata.id", "ID"),
                ("workflowVersion.workflow.name", "Workflow"),
                ("workflowVersion.version", "Version"),
                ("triggerAt", "Trigger At", lambda x: format_timestamp(x)),
                ("metadata.createdAt", "Created", lambda x: format_timestamp(x)),
            ]
            output_detail(scheduled, fields, title="Scheduled Run")

            # Show input if available
            input_data = scheduled.get("input")
            if input_data:
                click.echo("\nInput Data:")
                output_json(input_data)

            # Show additional metadata
            add_meta = scheduled.get("additionalMetadata")
            if add_meta:
                click.echo("\nAdditional Metadata:")
                output_json(add_meta)
        else:
            formatter.output(scheduled)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@scheduled.command("create")
@click.argument("workflow_id")
@click.option("--at", "-a", "trigger_at", required=True, help="When to trigger (ISO 8601 or relative: +1h, +30m, +1d)")
@click.option("--input", "-i", "input_data", help="Input data as JSON string")
@click.option("--input-file", type=click.Path(exists=True), help="Path to JSON file with input data")
@click.option("--metadata", "-m", multiple=True, help="Additional metadata (key=value format)")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def create_scheduled(
    ctx,
    workflow_id: str,
    trigger_at: str,
    input_data: Optional[str],
    input_file: Optional[str],
    metadata: tuple,
    output_format: str,
):
    """
    Schedule a workflow run.

    Schedules a workflow to run at a specific time in the future.

    WORKFLOW_ID is the workflow to schedule.

    Time can be specified as:
    - ISO 8601 timestamp: 2024-01-15T10:00:00Z
    - Relative time: +1h (in 1 hour), +30m (in 30 minutes), +1d (in 1 day)

    Examples:

        # Schedule for a specific time
        hatchet scheduled create my-workflow --at "2024-01-15T10:00:00Z"

        # Schedule in 1 hour
        hatchet scheduled create my-workflow --at "+1h"

        # Schedule in 30 minutes with input
        hatchet scheduled create my-workflow --at "+30m" --input '{"priority": "high"}'

        # Schedule for tomorrow
        hatchet scheduled create my-workflow --at "+1d" --metadata reason="daily-batch"
    """
    try:
        client: HatchetClient = ctx.obj["client"]

        # Parse trigger time
        try:
            parsed_time = parse_time_spec(trigger_at)
        except (ValueError, TypeError) as e:
            output_error(f"Invalid time specification: {e}")
            raise SystemExit(1)

        # Parse input data
        parsed_input = None
        if input_data:
            try:
                parsed_input = json.loads(input_data)
            except json.JSONDecodeError as e:
                output_error(f"Invalid JSON input: {e}")
                raise SystemExit(1)
        elif input_file:
            with open(input_file, "r") as f:
                try:
                    parsed_input = json.load(f)
                except json.JSONDecodeError as e:
                    output_error(f"Invalid JSON in file: {e}")
                    raise SystemExit(1)

        # Parse metadata
        additional_metadata = {}
        for m in metadata:
            if "=" in m:
                k, v = m.split("=", 1)
                additional_metadata[k] = v
            else:
                output_error(f"Invalid metadata format: {m}. Use key=value format.")
                raise SystemExit(1)

        result = client.schedule_workflow(
            workflow_id=workflow_id,
            trigger_at=parsed_time,
            input_data=parsed_input,
            additional_metadata=additional_metadata if additional_metadata else None,
        )

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            scheduled_id = result.get("metadata", {}).get("id", result.get("id", "unknown"))
            output_success(f"Workflow scheduled successfully!")
            click.echo(f"Scheduled ID: {scheduled_id}")
            click.echo(f"Trigger At: {parsed_time}")
            click.echo(f"Workflow: {workflow_id}")
        else:
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@scheduled.command("delete")
@click.argument("scheduled_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def delete_scheduled(ctx, scheduled_id: str, yes: bool):
    """
    Delete a scheduled run.

    Cancels a scheduled workflow run. The workflow will not be triggered.

    SCHEDULED_ID is the scheduled run UUID.

    Examples:

        # Delete with confirmation
        hatchet scheduled delete abc123-def456-...

        # Delete without confirmation
        hatchet scheduled delete abc123-def456-... --yes
    """
    try:
        if not yes:
            if not confirm("Are you sure you want to delete this scheduled run?"):
                click.echo("Cancelled.")
                return

        client: HatchetClient = ctx.obj["client"]
        client.delete_scheduled_run(scheduled_id)
        output_success(f"Scheduled run {scheduled_id} deleted successfully.")

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)
