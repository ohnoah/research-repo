"""
Worker Commands - Monitor workers in Hatchet.

Commands:
    list - List all workers
    get  - Get worker details
"""

from typing import Optional

import click

from ..client import HatchetClient
from ..exceptions import HatchetAPIError, HatchetConfigurationError
from ..output import (
    OutputFormatter,
    format_timestamp,
    output_error,
    output_table,
    output_detail,
    output_json,
    console,
    WORKER_STATUS_COLORS,
)
from rich.text import Text


def colorize_worker_status(status: str) -> Text:
    """Get colorized worker status text."""
    color = WORKER_STATUS_COLORS.get(status, "white")
    return Text(status, style=color)


@click.group()
def workers():
    """
    Monitor workers.

    Workers are the processes that execute workflow tasks. Use these commands
    to monitor worker health, status, and capabilities.

    Examples:

        # List all workers
        hatchet workers list

        # Get worker details
        hatchet workers get <worker-id>
    """
    pass


@workers.command("list")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def list_workers(ctx, output_format: str):
    """
    List all workers.

    Shows all workers registered with the tenant, including their status,
    last heartbeat, and supported actions.

    Examples:

        # List workers as table
        hatchet workers list

        # List as JSON for scripting
        hatchet workers list --format json
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.list_workers()

        workers_list = result.get("rows", result) if isinstance(result, dict) else result

        if not workers_list:
            click.echo("No workers found.")
            return

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            columns = [
                ("metadata.id", "ID", lambda x: x[:12] + "..." if x else "-"),
                ("name", "Name"),
                ("status", "Status", lambda x: str(colorize_worker_status(x)) if x else "-"),
                ("lastHeartbeatAt", "Last Heartbeat", lambda x: format_timestamp(x, relative=True) if x else "-"),
                ("maxRuns", "Max Runs", lambda x: str(x) if x is not None else "-"),
                ("availableRuns", "Available", lambda x: str(x) if x is not None else "-"),
            ]

            # Count active vs inactive
            active_count = sum(1 for w in workers_list if w.get("status") == "ACTIVE")
            total = len(workers_list)

            output_table(
                workers_list,
                columns,
                title=f"Workers ({active_count} active / {total} total)"
            )
        else:
            formatter.output(workers_list)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@workers.command("get")
@click.argument("worker_id")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def get_worker(ctx, worker_id: str, output_format: str):
    """
    Get worker details.

    Retrieves detailed information about a worker including its configuration,
    supported actions, and current status.

    WORKER_ID is the worker UUID.

    Examples:

        # Get worker details
        hatchet workers get abc123-def456-...

        # Get as JSON
        hatchet workers get abc123-def456-... --format json
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        worker = client.get_worker(worker_id)

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            fields = [
                ("metadata.id", "ID"),
                ("name", "Name"),
                ("status", "Status", lambda x: str(colorize_worker_status(x)) if x else "-"),
                ("lastHeartbeatAt", "Last Heartbeat", lambda x: format_timestamp(x) if x else "-"),
                ("metadata.createdAt", "Created", lambda x: format_timestamp(x)),
                ("maxRuns", "Max Concurrent Runs"),
                ("availableRuns", "Available Run Slots"),
                ("dispatcherId", "Dispatcher ID"),
            ]
            output_detail(worker, fields, title="Worker")

            # Show actions/steps this worker can handle
            actions = worker.get("actions", [])
            if actions:
                click.echo("\nSupported Actions:")
                for action in actions:
                    action_id = action.get("actionId", action) if isinstance(action, dict) else action
                    click.echo(f"  - {action_id}")

            # Show labels
            labels = worker.get("labels", [])
            if labels:
                click.echo("\nLabels:")
                for label in labels:
                    if isinstance(label, dict):
                        click.echo(f"  - {label.get('key', '')}: {label.get('value', '')}")
                    else:
                        click.echo(f"  - {label}")

            # Show recent step runs if available
            recent_step_runs = worker.get("recentStepRuns", [])
            if recent_step_runs:
                click.echo(f"\nRecent Step Runs ({len(recent_step_runs)}):")
                for sr in recent_step_runs[:5]:
                    sr_id = sr.get("id", "unknown")[:12]
                    status = sr.get("status", "UNKNOWN")
                    click.echo(f"  - {sr_id}... [{status}]")

        else:
            formatter.output(worker)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)
