"""
Hatchet CLI - Main entry point.

This is the main CLI application that provides access to all Hatchet
operations through a command-line interface.

Usage:
    hatchet [OPTIONS] COMMAND [ARGS]...
    hctl [OPTIONS] COMMAND [ARGS]...

Global Options:
    --api-token   API token for authentication
    --tenant      Tenant ID for operations
    --base-url    Hatchet API base URL
    --profile     Configuration profile to use
    --format      Output format (table, json, yaml)
    --no-color    Disable colored output
    --version     Show version information
    --help        Show help message

For more information on a specific command:
    hatchet COMMAND --help
"""

from __future__ import annotations

import sys
from typing import Optional

import click

from . import __version__
from .client import HatchetClient
from .config import get_config
from .exceptions import HatchetCLIError, HatchetConfigurationError
from .output import output_error, console

from .commands import (
    workflows,
    runs,
    steps,
    events,
    workers,
    tokens,
    tenant,
    crons,
    scheduled,
    config,
)


CONTEXT_SETTINGS = dict(
    help_option_names=["-h", "--help"],
    max_content_width=100,
)


class HatchetContext:
    """Context object passed to all commands."""

    def __init__(self):
        self.client: Optional[HatchetClient] = None
        self.output_format: str = "table"
        self.use_color: bool = True


pass_context = click.make_pass_decorator(HatchetContext, ensure=True)


@click.group(context_settings=CONTEXT_SETTINGS)
@click.option(
    "--api-token",
    envvar="HATCHET_API_TOKEN",
    help="API token for authentication. Can also be set via HATCHET_API_TOKEN env var.",
)
@click.option(
    "--mode",
    type=click.Choice(["raw", "gateway"]),
    envvar="HATCHET_MODE",
    default=None,
    help="Connection mode: raw (direct) or gateway",
)
@click.option(
    "--gateway-url",
    envvar="GATEWAY_URL",
    help="Gateway base URL (for gateway mode).",
)
@click.option(
    "--gateway-token",
    envvar="GATEWAY_TOKEN",
    help="Gateway token (for gateway mode).",
)
@click.option(
    "--tenant", "-t",
    "tenant_id",
    envvar="HATCHET_TENANT_ID",
    help="Tenant ID for operations. Can also be set via HATCHET_TENANT_ID env var.",
)
@click.option(
    "--base-url", "-u",
    envvar="HATCHET_BASE_URL",
    help="Hatchet API base URL. Defaults to https://app.hatchet.run",
)
@click.option(
    "--profile", "-p",
    help="Configuration profile to use. See 'hatchet config profile list'.",
)
@click.option(
    "--format", "-f",
    "output_format",
    type=click.Choice(["table", "json", "yaml"]),
    help="Output format. Overrides config setting.",
)
@click.option(
    "--no-color",
    is_flag=True,
    help="Disable colored output.",
)
@click.version_option(
    version=__version__,
    prog_name="hatchet-cli",
    message="%(prog)s %(version)s",
)
@click.pass_context
def cli(
    ctx,
    api_token: Optional[str],
    mode: Optional[str],
    gateway_url: Optional[str],
    gateway_token: Optional[str],
    tenant_id: Optional[str],
    base_url: Optional[str],
    profile: Optional[str],
    output_format: Optional[str],
    no_color: bool,
):
    """
    Hatchet CLI - Command-line interface for Hatchet workflow orchestration.

    Hatchet is a modern orchestration platform for background tasks and
    workflow automation. This CLI provides access to all Hatchet operations.

    \b
    GETTING STARTED
    ---------------
    1. Initialize your configuration:
       $ hatchet config init

    2. Or set environment variables:
       $ export HATCHET_API_TOKEN=your-token
       $ export HATCHET_TENANT_ID=your-tenant-id

    \b
    COMMON COMMANDS
    ---------------
    workflows list     List all workflows
    runs list          List workflow runs
    runs list -s FAILED  List failed runs
    runs get <id>      Get run details
    steps logs <id>    View step logs
    events create      Create an event

    \b
    DOCUMENTATION
    -------------
    For full documentation, visit: https://docs.hatchet.run

    \b
    EXAMPLES
    --------
    # List all workflows
    $ hatchet workflows list

    # Trigger a workflow
    $ hatchet workflows trigger my-workflow --input '{"key": "value"}'

    # List failed runs from the last day
    $ hatchet runs list --status FAILED --created-after 2024-01-15T00:00:00Z

    # Get run details
    $ hatchet runs get abc123-def456-...

    # View step logs
    $ hatchet steps logs xyz789-...

    # Create an event
    $ hatchet events create user:signup --data '{"userId": "123"}'

    # Cancel running workflows
    $ hatchet runs cancel run1-id run2-id

    # Replay failed runs
    $ hatchet runs replay run1-id run2-id
    """
    ctx.ensure_object(dict)

    # Load configuration
    try:
        cfg = get_config()
    except Exception:
        cfg = None

    # Determine settings with precedence: CLI args > env vars > config file
    final_base_url = base_url
    final_api_token = api_token
    final_tenant_id = tenant_id
    final_gateway_url = gateway_url
    final_gateway_token = gateway_token

    if cfg:
        profile_config = cfg.get_profile(profile)

        if not mode:
            mode = cfg.get_mode(profile)

        if not final_base_url:
            final_base_url = cfg.get_base_url(profile)
        if not final_api_token:
            final_api_token = cfg.get_api_token(profile)
        if not final_tenant_id:
            final_tenant_id = cfg.get_tenant_id(profile)
        if not final_gateway_url:
            final_gateway_url = cfg.get_gateway_url(profile)
        if not final_gateway_token:
            final_gateway_token = cfg.get_gateway_token(profile)

        if not output_format:
            output_format = cfg.get_output_format()

    # Set up context
    ctx.obj = {
        "api_token": final_api_token,
        "tenant_id": final_tenant_id,
        "base_url": final_base_url,
        "output_format": output_format or "table",
        "use_color": not no_color,
        "mode": mode or "raw",
        "gateway_url": final_gateway_url,
        "gateway_token": final_gateway_token,
        "client": None,
    }

    # Don't require authentication for config commands
    if ctx.invoked_subcommand in ("config", None):
        return

    # Create API client
    try:
        if (mode or "raw") == "gateway":
            from .gateway_client import GatewayHatchetClient

            ctx.obj["client"] = GatewayHatchetClient(
                base_url=final_gateway_url,
                gateway_token=final_gateway_token,
                profile=profile,
            )
        else:
            ctx.obj["client"] = HatchetClient(
                base_url=final_base_url,
                api_token=final_api_token,
                tenant_id=final_tenant_id,
            )
    except HatchetConfigurationError as e:
        output_error(str(e))
        click.echo("\nTo set up authentication, either:")
        click.echo("  1. Run: hatchet config init")
        click.echo("  2. Set HATCHET_API_TOKEN environment variable")
        click.echo("  3. Use --api-token flag")
        raise SystemExit(1)


# Register command groups
cli.add_command(workflows)
cli.add_command(runs)
cli.add_command(steps)
cli.add_command(events)
cli.add_command(workers)
cli.add_command(tokens)
cli.add_command(tenant)
cli.add_command(crons)
cli.add_command(scheduled)
cli.add_command(config)


# Aliases for common commands
@cli.command("status")
@click.pass_context
def quick_status(ctx):
    """
    Quick status overview.

    Shows a summary of recent workflow runs and worker status.

    Alias for: runs list --limit 5 + workers list
    """
    try:
        client: HatchetClient = ctx.obj["client"]

        # Get recent runs
        click.echo("Recent Workflow Runs:")
        click.echo("-" * 40)
        try:
            runs_result = client.list_workflow_runs(limit=5)
            runs_list = runs_result.get("rows", [])
            if runs_list:
                for run in runs_list:
                    run_id = run.get("metadata", {}).get("id", "unknown")[:12]
                    workflow = run.get("workflowVersion", {}).get("workflow", {}).get("name", "unknown")
                    status = run.get("status", "UNKNOWN")
                    click.echo(f"  [{status}] {workflow} ({run_id}...)")
            else:
                click.echo("  No recent runs")
        except Exception as e:
            click.echo(f"  Error fetching runs: {e}")

        click.echo()

        # Get workers
        click.echo("Workers:")
        click.echo("-" * 40)
        try:
            workers_result = client.list_workers()
            workers_list = workers_result.get("rows", workers_result) if isinstance(workers_result, dict) else workers_result
            if workers_list:
                active = sum(1 for w in workers_list if w.get("status") == "ACTIVE")
                total = len(workers_list)
                click.echo(f"  {active} active / {total} total")
            else:
                click.echo("  No workers registered")
        except Exception as e:
            click.echo(f"  Error fetching workers: {e}")

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)


@cli.command("health")
@click.pass_context
def health_check(ctx):
    """
    Check API health.

    Verifies connectivity to the Hatchet API.
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        client.check_health()
        click.echo("[green]API is healthy[/green]", color=True)

        # Also verify authentication
        try:
            user = client.get_current_user()
            email = user.get("email", "unknown")
            click.echo(f"Authenticated as: {email}")
        except Exception:
            click.echo("Authentication: Could not verify user")

    except Exception as e:
        output_error(f"API health check failed: {e}")
        raise SystemExit(1)


@cli.command("version")
def show_version():
    """Show version information."""
    click.echo(f"hatchet-cli {__version__}")
    click.echo("https://github.com/hatchet-dev/hatchet")


@cli.command("use")
@click.argument("profile_name")
def use_profile(profile_name: str):
    """
    Switch to a different profile (quick alias for 'config profile use').

    Quickly switch between different Hatchet accounts/tenants.

    Examples:

        hatchet use production
        hatchet use staging
    """
    from .output import output_success, output_error

    try:
        cfg = get_config()

        profiles = cfg.list_profiles()
        if profile_name not in profiles:
            output_error(f"Profile '{profile_name}' does not exist.")
            if profiles:
                click.echo(f"Available profiles: {', '.join(profiles.keys())}")
            raise SystemExit(1)

        cfg.default_profile = profile_name
        cfg.save()

        profile_data = profiles[profile_name]
        tenant_name = profile_data.get("tenant_name", "")
        tenant_id = profile_data.get("tenant_id", "")

        if tenant_name:
            output_success(f"Switched to '{profile_name}' ({tenant_name})")
        elif tenant_id:
            output_success(f"Switched to '{profile_name}' (tenant: {tenant_id[:12]}...)")
        else:
            output_success(f"Switched to '{profile_name}'")

    except SystemExit:
        raise
    except Exception as e:
        output_error(f"Failed to switch profile: {e}")
        raise SystemExit(1)


@cli.command("whoami")
@click.pass_context
def whoami(ctx):
    """
    Show current profile and authentication info.

    Displays which profile is active, the tenant name, and authenticated user.

    Examples:

        hatchet whoami
    """
    from .output import output_error, output_info

    try:
        cfg = get_config()
        profile_name = cfg.default_profile
        profile_data = cfg.get_profile(profile_name)

        click.echo(f"Profile:     {profile_name}")
        click.echo(f"Base URL:    {profile_data.get('base_url', 'not set')}")

        tenant_name = profile_data.get("tenant_name", "")
        tenant_id = profile_data.get("tenant_id", "")
        if tenant_name:
            click.echo(f"Tenant:      {tenant_name}")
        elif tenant_id:
            click.echo(f"Tenant ID:   {tenant_id}")

        # Try to get user info if client is available
        client = ctx.obj.get("client") if ctx.obj else None
        if client:
            try:
                user = client.get_current_user()
                email = user.get("email", "unknown")
                click.echo(f"User:        {email}")

                # Also try to fetch and cache tenant name if we don't have it
                if tenant_id and not tenant_name:
                    try:
                        tenant_info = client.get_tenant(tenant_id)
                        fetched_name = tenant_info.get("name", "")
                        if fetched_name:
                            click.echo(f"Tenant:      {fetched_name}")
                            # Cache it in config
                            profile_data["tenant_name"] = fetched_name
                            cfg.set_profile(profile_name, profile_data)
                            cfg.save()
                    except Exception:
                        pass
            except Exception:
                click.echo("User:        (unable to fetch)")
        else:
            click.echo("User:        (not authenticated)")

    except Exception as e:
        output_error(f"Failed to get profile info: {e}")
        raise SystemExit(1)


def main():
    """Main entry point for the CLI."""
    try:
        cli(obj={})
    except HatchetCLIError as e:
        output_error(str(e))
        sys.exit(1)
    except KeyboardInterrupt:
        click.echo("\nOperation cancelled.")
        sys.exit(130)
    except Exception as e:
        output_error(f"Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
