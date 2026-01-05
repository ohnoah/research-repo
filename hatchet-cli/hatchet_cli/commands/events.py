"""
Event Commands - Manage events in Hatchet.

Commands:
    list   - List events with filtering
    get    - Get event details
    data   - Get event payload data
    create - Create a new event
    bulk   - Create multiple events
    replay - Replay events
    keys   - List event keys
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
def events():
    """
    Manage events.

    Events are triggers that start workflow runs. Use these commands
    to list, create, and replay events.

    Examples:

        # List all events
        hatchet events list

        # Create an event
        hatchet events create user:signup --data '{"userId": "123"}'

        # Replay an event
        hatchet events replay <event-id>
    """
    pass


@events.command("list")
@click.option("--key", "-k", multiple=True, help="Filter by event key (can specify multiple)")
@click.option("--workflow", "-w", multiple=True, help="Filter by workflow ID (can specify multiple)")
@click.option("--status", "-s", multiple=True, help="Filter by status (can specify multiple)")
@click.option("--search", "-q", help="Search term")
@click.option("--metadata", "-m", multiple=True, help="Filter by metadata (key:value format)")
@click.option("--order-by", type=click.Choice(["createdAt"]), default="createdAt", help="Field to order by")
@click.option("--order", type=click.Choice(["ASC", "DESC"]), default="DESC", help="Order direction")
@click.option("--limit", "-l", default=20, help="Maximum number of events to return")
@click.option("--offset", default=0, help="Pagination offset")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def list_events(
    ctx,
    key: tuple,
    workflow: tuple,
    status: tuple,
    search: Optional[str],
    metadata: tuple,
    order_by: str,
    order: str,
    limit: int,
    offset: int,
    output_format: str,
):
    """
    List events with filtering.

    Shows events that have triggered workflow runs.

    Examples:

        # List all events
        hatchet events list

        # Filter by event key
        hatchet events list --key user:signup

        # Filter by multiple keys
        hatchet events list --key user:signup --key user:login

        # Search events
        hatchet events list --search "user123"

        # Filter by workflow
        hatchet events list --workflow my-workflow
    """
    try:
        client: HatchetClient = ctx.obj["client"]

        metadata_list = list(metadata) if metadata else None

        result = client.list_events(
            keys=list(key) if key else None,
            workflows=list(workflow) if workflow else None,
            statuses=list(status) if status else None,
            search=search,
            additional_metadata=metadata_list,
            order_by_field=order_by,
            order_by_direction=order,
            limit=limit,
            offset=offset,
        )

        events_list = result.get("rows", [])

        if not events_list:
            click.echo("No events found.")
            return

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            columns = [
                ("metadata.id", "ID", lambda x: x[:12] + "..." if x else "-"),
                ("key", "Key"),
                ("metadata.createdAt", "Created", lambda x: format_timestamp(x, relative=True)),
                ("workflowRuns", "Runs", lambda x: str(len(x)) if x else "0"),
            ]
            output_table(events_list, columns, title=f"Events (showing {len(events_list)})")

            if len(events_list) >= limit:
                click.echo(f"\nTip: Use --offset {offset + limit} to see more results")
        else:
            formatter.output(events_list)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@events.command("get")
@click.argument("event_id")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def get_event(ctx, event_id: str, output_format: str):
    """
    Get event details.

    Retrieves detailed information about an event.

    EVENT_ID is the event UUID.

    Examples:

        hatchet events get abc123-def456-...
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        event = client.get_event(event_id)

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            fields = [
                ("metadata.id", "ID"),
                ("key", "Key"),
                ("metadata.createdAt", "Created", lambda x: format_timestamp(x)),
            ]
            output_detail(event, fields, title="Event")

            # Show workflow runs triggered
            runs = event.get("workflowRuns", [])
            if runs:
                click.echo(f"\nTriggered {len(runs)} workflow run(s):")
                for run in runs[:5]:  # Show first 5
                    run_id = run.get("id", "unknown")
                    workflow = run.get("workflowVersion", {}).get("workflow", {}).get("name", "unknown")
                    click.echo(f"  - {run_id[:12]}... ({workflow})")
                if len(runs) > 5:
                    click.echo(f"  ... and {len(runs) - 5} more")
        else:
            formatter.output(event)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@events.command("data")
@click.argument("event_id")
@click.option("--format", "-f", "output_format", type=click.Choice(["json", "yaml"]), default="json", help="Output format")
@click.pass_context
def event_data(ctx, event_id: str, output_format: str):
    """
    Get event payload data.

    Shows the data/payload that was sent with the event.

    EVENT_ID is the event UUID.

    Examples:

        hatchet events data abc123-def456-...
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.get_event_data(event_id)

        formatter = OutputFormatter(output_format)
        formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@events.command("create")
@click.argument("key")
@click.option("--data", "-d", "payload", help="Event payload as JSON string")
@click.option("--data-file", type=click.Path(exists=True), help="Path to JSON file with payload")
@click.option("--metadata", "-m", multiple=True, help="Additional metadata (key=value format)")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def create_event(
    ctx,
    key: str,
    payload: Optional[str],
    data_file: Optional[str],
    metadata: tuple,
    output_format: str,
):
    """
    Create a new event.

    Creates an event that will trigger any workflows listening for the specified key.

    KEY is the event type/key (e.g., "user:signup", "order:created").

    Examples:

        # Create event with inline data
        hatchet events create user:signup --data '{"userId": "123", "email": "user@example.com"}'

        # Create event with data from file
        hatchet events create order:created --data-file ./order.json

        # Create event with metadata
        hatchet events create user:signup -d '{"userId": "123"}' -m env=production

        # Create event without payload
        hatchet events create system:healthcheck
    """
    try:
        client: HatchetClient = ctx.obj["client"]

        # Parse payload
        parsed_payload = {}
        if payload:
            try:
                parsed_payload = json.loads(payload)
            except json.JSONDecodeError as e:
                output_error(f"Invalid JSON payload: {e}")
                raise SystemExit(1)
        elif data_file:
            with open(data_file, "r") as f:
                try:
                    parsed_payload = json.load(f)
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

        result = client.create_event(
            key=key,
            payload=parsed_payload,
            additional_metadata=additional_metadata if additional_metadata else None,
        )

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            event_id = result.get("metadata", {}).get("id", result.get("id", "unknown"))
            output_success(f"Event created successfully!")
            click.echo(f"Event ID: {event_id}")
            click.echo(f"Key: {key}")
        else:
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@events.command("bulk")
@click.option("--file", "-F", "events_file", type=click.Path(exists=True), required=True, help="Path to JSON file with events array")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def bulk_create_events(ctx, events_file: str, output_format: str):
    """
    Create multiple events in bulk.

    Reads events from a JSON file and creates them all at once.
    The file should contain an array of event objects with 'key' and 'payload' fields.

    Examples:

        # events.json:
        # [
        #   {"key": "user:signup", "payload": {"userId": "1"}},
        #   {"key": "user:signup", "payload": {"userId": "2"}}
        # ]

        hatchet events bulk --file events.json
    """
    try:
        with open(events_file, "r") as f:
            try:
                events_data = json.load(f)
            except json.JSONDecodeError as e:
                output_error(f"Invalid JSON in file: {e}")
                raise SystemExit(1)

        if not isinstance(events_data, list):
            output_error("Events file must contain a JSON array of events")
            raise SystemExit(1)

        client: HatchetClient = ctx.obj["client"]
        result = client.create_events_bulk(events_data)

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            output_success(f"Created {len(events_data)} event(s) successfully!")
        else:
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@events.command("replay")
@click.argument("event_ids", nargs=-1, required=True)
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def replay_events(ctx, event_ids: tuple, yes: bool, output_format: str):
    """
    Replay events.

    Re-triggers workflows for the specified events. Useful for
    reprocessing failed events or debugging.

    EVENT_IDS are the event UUIDs to replay (space-separated).

    Examples:

        # Replay a single event
        hatchet events replay abc123-def456-...

        # Replay multiple events
        hatchet events replay event1-id event2-id

        # Replay without confirmation
        hatchet events replay abc123-def456-... --yes
    """
    try:
        if not yes:
            if not confirm(f"Are you sure you want to replay {len(event_ids)} event(s)?"):
                click.echo("Cancelled.")
                return

        client: HatchetClient = ctx.obj["client"]
        result = client.replay_events(list(event_ids))

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            output_success(f"Replayed {len(event_ids)} event(s).")
        else:
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@events.command("keys")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def list_event_keys(ctx, output_format: str):
    """
    List all event keys.

    Shows all unique event keys that have been used in the tenant.
    Useful for discovering available event types.

    Examples:

        hatchet events keys
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.list_event_keys()

        keys = result.get("rows", result) if isinstance(result, dict) else result

        if not keys:
            click.echo("No event keys found.")
            return

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            click.echo("Event Keys:")
            if isinstance(keys, list):
                for key in keys:
                    if isinstance(key, dict):
                        click.echo(f"  - {key.get('key', key)}")
                    else:
                        click.echo(f"  - {key}")
            else:
                output_json(keys)
        else:
            formatter.output(keys)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)
