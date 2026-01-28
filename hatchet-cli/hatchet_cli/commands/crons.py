"""
Cron Commands - Manage cron-triggered workflows in Hatchet.

Commands:
    list   - List cron triggers
    get    - Get cron trigger details
    create - Create a cron trigger
    delete - Delete a cron trigger
"""

import json
from typing import Optional

import click

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


@click.group()
def crons():
    """
    Manage cron-triggered workflows.

    Cron triggers automatically run workflows on a schedule.
    Use these commands to create, list, and manage cron jobs.

    Examples:

        # List all cron triggers
        hatchet crons list

        # Create a cron trigger
        hatchet crons create my-workflow --cron "0 9 * * *"

        # Delete a cron trigger
        hatchet crons delete <cron-id>
    """
    pass


@crons.command("list")
@click.option("--workflow", "-w", help="Filter by workflow ID")
@click.option("--metadata", "-m", multiple=True, help="Filter by metadata (key:value format)")
@click.option("--order-by", type=click.Choice(["createdAt"]), default="createdAt", help="Field to order by")
@click.option("--order", type=click.Choice(["ASC", "DESC"]), default="DESC", help="Order direction")
@click.option("--limit", "-l", default=20, help="Maximum number of crons to return")
@click.option("--offset", default=0, help="Pagination offset")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def list_crons(
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
    List cron triggers.

    Shows all cron-triggered workflows for the tenant.

    Examples:

        # List all crons
        hatchet crons list

        # Filter by workflow
        hatchet crons list --workflow my-workflow
    """
    try:
        client: HatchetClient = ctx.obj["client"]

        metadata_list = list(metadata) if metadata else None

        result = client.list_crons(
            workflow_id=workflow,
            additional_metadata=metadata_list,
            order_by_field=order_by,
            order_by_direction=order,
            limit=limit,
            offset=offset,
        )

        crons_list = result.get("rows", [])

        if not crons_list:
            click.echo("No cron triggers found.")
            return

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            columns = [
                ("metadata.id", "ID", lambda x: x[:12] + "..." if x else "-"),
                ("name", "Name"),
                ("cron", "Schedule"),
                ("workflowVersion.workflow.name", "Workflow"),
                ("metadata.createdAt", "Created", lambda x: format_timestamp(x)),
            ]
            output_table(crons_list, columns, title=f"Cron Triggers ({len(crons_list)})")
        else:
            formatter.output(crons_list)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@crons.command("get")
@click.argument("cron_id")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def get_cron(ctx, cron_id: str, output_format: str):
    """
    Get cron trigger details.

    Retrieves detailed information about a cron trigger.

    CRON_ID is the cron trigger UUID.

    Examples:

        hatchet crons get abc123-def456-...
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        cron = client.get_cron(cron_id)

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            fields = [
                ("metadata.id", "ID"),
                ("name", "Name"),
                ("cron", "Schedule"),
                ("workflowVersion.workflow.name", "Workflow"),
                ("workflowVersion.version", "Version"),
                ("metadata.createdAt", "Created", lambda x: format_timestamp(x)),
                ("metadata.updatedAt", "Updated", lambda x: format_timestamp(x)),
            ]
            output_detail(cron, fields, title="Cron Trigger")

            # Show input if available
            input_data = cron.get("input")
            if input_data:
                click.echo("\nInput Data:")
                output_json(input_data)

            # Show additional metadata
            add_meta = cron.get("additionalMetadata")
            if add_meta:
                click.echo("\nAdditional Metadata:")
                output_json(add_meta)
        else:
            formatter.output(cron)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@crons.command("create")
@click.argument("workflow_id")
@click.option("--cron", "-c", "cron_expression", required=True, help="Cron expression (e.g., '0 9 * * *' for 9am daily)")
@click.option("--name", "-n", help="Name for the cron trigger")
@click.option("--input", "-i", "input_data", help="Input data as JSON string")
@click.option("--input-file", type=click.Path(exists=True), help="Path to JSON file with input data")
@click.option("--metadata", "-m", multiple=True, help="Additional metadata (key=value format)")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def create_cron(
    ctx,
    workflow_id: str,
    cron_expression: str,
    name: Optional[str],
    input_data: Optional[str],
    input_file: Optional[str],
    metadata: tuple,
    output_format: str,
):
    """
    Create a cron trigger.

    Creates a new cron schedule to automatically trigger a workflow.

    WORKFLOW_ID is the workflow to trigger.

    Cron Expression Format:
        ┌───────────── minute (0 - 59)
        │ ┌───────────── hour (0 - 23)
        │ │ ┌───────────── day of month (1 - 31)
        │ │ │ ┌───────────── month (1 - 12)
        │ │ │ │ ┌───────────── day of week (0 - 6) (Sunday to Saturday)
        │ │ │ │ │
        * * * * *

    Examples:

        # Run every day at 9am
        hatchet crons create my-workflow --cron "0 9 * * *"

        # Run every hour
        hatchet crons create my-workflow --cron "0 * * * *" --name "Hourly Job"

        # Run every Monday at 8am with input
        hatchet crons create my-workflow --cron "0 8 * * 1" --input '{"type": "weekly"}'

        # Run every 5 minutes
        hatchet crons create my-workflow --cron "*/5 * * * *"
    """
    try:
        client: HatchetClient = ctx.obj["client"]

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

        result = client.create_cron(
            workflow_id=workflow_id,
            cron_expression=cron_expression,
            cron_name=name,
            input_data=parsed_input,
            additional_metadata=additional_metadata if additional_metadata else None,
        )

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            cron_id = result.get("metadata", {}).get("id", result.get("id", "unknown"))
            output_success(f"Cron trigger created successfully!")
            click.echo(f"Cron ID: {cron_id}")
            click.echo(f"Schedule: {cron_expression}")
            click.echo(f"Workflow: {workflow_id}")
        else:
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@crons.command("delete")
@click.argument("cron_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def delete_cron(ctx, cron_id: str, yes: bool):
    """
    Delete a cron trigger.

    Permanently removes a cron trigger. The workflow will no longer
    be triggered on this schedule.

    CRON_ID is the cron trigger UUID.

    Examples:

        # Delete with confirmation
        hatchet crons delete abc123-def456-...

        # Delete without confirmation
        hatchet crons delete abc123-def456-... --yes
    """
    try:
        if not yes:
            if not confirm("Are you sure you want to delete this cron trigger?"):
                click.echo("Cancelled.")
                return

        client: HatchetClient = ctx.obj["client"]
        client.delete_cron(cron_id)
        output_success(f"Cron trigger {cron_id} deleted successfully.")

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)
