"""
API Token Commands - Manage API tokens in Hatchet.

Commands:
    list   - List all API tokens
    create - Create a new API token
    revoke - Revoke an API token
"""

from typing import Optional

import click

from ..client import HatchetClient
from ..exceptions import HatchetAPIError, HatchetConfigurationError
from ..output import (
    OutputFormatter,
    format_timestamp,
    output_error,
    output_success,
    output_warning,
    output_table,
    output_detail,
    confirm,
    console,
)


@click.group()
def tokens():
    """
    Manage API tokens.

    API tokens are used to authenticate with the Hatchet API. Use these
    commands to create, list, and revoke tokens.

    Examples:

        # List all tokens
        hatchet tokens list

        # Create a new token
        hatchet tokens create --name "CI/CD Token"

        # Revoke a token
        hatchet tokens revoke <token-id>
    """
    pass


@tokens.command("list")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def list_tokens(ctx, output_format: str):
    """
    List all API tokens.

    Shows all API tokens for the tenant. Token values are masked for security.

    Examples:

        hatchet tokens list
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.list_api_tokens()

        tokens_list = result.get("rows", result) if isinstance(result, dict) else result

        if not tokens_list:
            click.echo("No API tokens found.")
            return

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            columns = [
                ("metadata.id", "ID", lambda x: x[:12] + "..." if x else "-"),
                ("name", "Name"),
                ("metadata.createdAt", "Created", lambda x: format_timestamp(x)),
                ("expiresAt", "Expires", lambda x: format_timestamp(x) if x else "Never"),
            ]
            output_table(tokens_list, columns, title="API Tokens")
        else:
            formatter.output(tokens_list)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@tokens.command("create")
@click.option("--name", "-n", required=True, help="Name/description for the token")
@click.option("--expires", "-e", help="Expiration duration (e.g., '30d', '1y', '90d')")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def create_token(ctx, name: str, expires: Optional[str], output_format: str):
    """
    Create a new API token.

    Creates a new API token for authenticating with the Hatchet API.
    The token value is only shown once, so make sure to save it.

    Examples:

        # Create a token with a name
        hatchet tokens create --name "CI/CD Token"

        # Create a token that expires in 30 days
        hatchet tokens create --name "Temp Token" --expires 30d

        # Create a token that expires in 1 year
        hatchet tokens create --name "Long-lived Token" --expires 1y
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.create_api_token(name=name, expires_in=expires)

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            output_success("API token created successfully!")
            output_warning("Save this token now - it won't be shown again!")
            click.echo()

            # The token value
            token = result.get("token", result.get("value", ""))
            if token:
                console.print(f"[bold]Token:[/bold] {token}")
            else:
                console.print(f"[bold]Token data:[/bold]")
                for key, value in result.items():
                    if key not in ("metadata", "tenant"):
                        console.print(f"  {key}: {value}")

            click.echo()
            click.echo("To use this token, set the environment variable:")
            click.echo(f"  export HATCHET_API_TOKEN={token or '<token>'}")
        else:
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@tokens.command("revoke")
@click.argument("token_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def revoke_token(ctx, token_id: str, yes: bool):
    """
    Revoke an API token.

    Permanently revokes an API token. Any applications using this token
    will no longer be able to authenticate.

    TOKEN_ID is the token UUID (can be found with 'tokens list').

    Examples:

        # Revoke with confirmation
        hatchet tokens revoke abc123-def456-...

        # Revoke without confirmation
        hatchet tokens revoke abc123-def456-... --yes
    """
    try:
        if not yes:
            output_warning("Revoking this token will break any applications using it.")
            if not confirm("Are you sure you want to revoke this token?"):
                click.echo("Cancelled.")
                return

        client: HatchetClient = ctx.obj["client"]
        client.revoke_api_token(token_id)
        output_success(f"Token {token_id} revoked successfully.")

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)
