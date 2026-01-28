"""
Tenant Commands - Manage tenant settings in Hatchet.

Commands:
    info      - Get tenant information
    members   - List tenant members
    metrics   - Get queue and task metrics
    ratelimits - List rate limits
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
)


@click.group()
def tenant():
    """
    Manage tenant settings.

    Tenants are workspaces that contain workflows, runs, and team members.
    Use these commands to view tenant info, members, and metrics.

    Examples:

        # Get tenant info
        hatchet tenant info

        # List team members
        hatchet tenant members

        # View queue metrics
        hatchet tenant metrics
    """
    pass


@tenant.command("info")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def tenant_info(ctx, output_format: str):
    """
    Get tenant information.

    Shows details about the current tenant including name, slug, and settings.

    Examples:

        hatchet tenant info
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.get_tenant()

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            fields = [
                ("metadata.id", "ID"),
                ("name", "Name"),
                ("slug", "Slug"),
                ("metadata.createdAt", "Created", lambda x: format_timestamp(x)),
                ("metadata.updatedAt", "Updated", lambda x: format_timestamp(x)),
            ]
            output_detail(result, fields, title="Tenant")

            # Show alerting settings if available
            alerting = result.get("alertMemberEmails")
            if alerting is not None:
                click.echo(f"\nAlert Member Emails: {'Enabled' if alerting else 'Disabled'}")

        else:
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@tenant.command("members")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def tenant_members(ctx, output_format: str):
    """
    List tenant members.

    Shows all team members who have access to this tenant.

    Examples:

        hatchet tenant members
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.list_tenant_members()

        members = result.get("rows", result) if isinstance(result, dict) else result

        if not members:
            click.echo("No members found.")
            return

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            columns = [
                ("user.email", "Email"),
                ("user.name", "Name"),
                ("role", "Role"),
                ("metadata.createdAt", "Joined", lambda x: format_timestamp(x)),
            ]
            output_table(members, columns, title="Tenant Members")
        else:
            formatter.output(members)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@tenant.command("metrics")
@click.option("--type", "-t", "metric_type", type=click.Choice(["queue", "tasks", "all"]), default="all", help="Type of metrics to show")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def tenant_metrics(ctx, metric_type: str, output_format: str):
    """
    Get queue and task metrics.

    Shows metrics about workflow queues and task execution.

    Examples:

        # Get all metrics
        hatchet tenant metrics

        # Get only queue metrics
        hatchet tenant metrics --type queue

        # Get only task stats
        hatchet tenant metrics --type tasks
    """
    try:
        client: HatchetClient = ctx.obj["client"]

        results = {}

        if metric_type in ("queue", "all"):
            results["queue_metrics"] = client.get_queue_metrics()

        if metric_type in ("tasks", "all"):
            results["task_stats"] = client.get_task_stats()

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            if "queue_metrics" in results:
                click.echo("Queue Metrics")
                click.echo("=" * 40)
                qm = results["queue_metrics"]
                if isinstance(qm, dict):
                    for key, value in qm.items():
                        if isinstance(value, (dict, list)):
                            click.echo(f"\n{key}:")
                            output_json(value)
                        else:
                            click.echo(f"  {key}: {value}")
                else:
                    output_json(qm)
                click.echo()

            if "task_stats" in results:
                click.echo("Task Statistics")
                click.echo("=" * 40)
                ts = results["task_stats"]
                if isinstance(ts, dict):
                    for key, value in ts.items():
                        if isinstance(value, (dict, list)):
                            click.echo(f"\n{key}:")
                            output_json(value)
                        else:
                            click.echo(f"  {key}: {value}")
                else:
                    output_json(ts)
        else:
            formatter.output(results)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@tenant.command("ratelimits")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def tenant_ratelimits(ctx, output_format: str):
    """
    List rate limits.

    Shows all rate limit configurations for the tenant.

    Examples:

        hatchet tenant ratelimits
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.list_rate_limits()

        limits = result.get("rows", result) if isinstance(result, dict) else result

        if not limits:
            click.echo("No rate limits configured.")
            return

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            if isinstance(limits, list):
                columns = [
                    ("key", "Key"),
                    ("limitValue", "Limit"),
                    ("value", "Current"),
                    ("window", "Window"),
                ]
                output_table(limits, columns, title="Rate Limits")
            else:
                output_json(limits)
        else:
            formatter.output(limits)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@tenant.command("user")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def current_user(ctx, output_format: str):
    """
    Get current user information.

    Shows details about the currently authenticated user.

    Examples:

        hatchet tenant user
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.get_current_user()

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            fields = [
                ("metadata.id", "ID"),
                ("email", "Email"),
                ("name", "Name"),
                ("emailVerified", "Email Verified", lambda x: "Yes" if x else "No"),
                ("metadata.createdAt", "Created", lambda x: format_timestamp(x)),
            ]
            output_detail(result, fields, title="Current User")
        else:
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@tenant.command("memberships")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def user_memberships(ctx, output_format: str):
    """
    List tenant memberships for current user.

    Shows all tenants the current user has access to.

    Examples:

        hatchet tenant memberships
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.list_memberships()

        memberships = result.get("rows", result) if isinstance(result, dict) else result

        if not memberships:
            click.echo("No tenant memberships found.")
            return

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            columns = [
                ("tenant.name", "Tenant"),
                ("tenant.slug", "Slug"),
                ("role", "Role"),
                ("tenant.metadata.id", "Tenant ID"),
            ]
            output_table(memberships, columns, title="Tenant Memberships")

            click.echo("\nTo switch tenants, use: --tenant <tenant-id>")
        else:
            formatter.output(memberships)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)
