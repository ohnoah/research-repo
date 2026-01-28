"""
Config Commands - Manage CLI configuration.

Commands:
    init    - Initialize configuration
    show    - Show current configuration
    set     - Set a configuration value
    profile - Manage configuration profiles
"""

from pathlib import Path
from typing import Optional

import click

from ..config import Config, get_config, setup_profile, DEFAULT_CONFIG_FILE
from ..output import output_error, output_success, output_warning, output_info, console


@click.group()
def config():
    """
    Manage CLI configuration.

    Configure API credentials, default settings, and profiles for
    different Hatchet environments.

    Configuration is stored in ~/.hatchet/config.yaml

    Examples:

        # Initialize configuration
        hatchet config init

        # Show current config
        hatchet config show

        # Create a new profile
        hatchet config profile create production
    """
    pass


@config.command("init")
@click.option("--base-url", "-u", default="https://app.hatchet.run", help="Hatchet API base URL")
@click.option("--api-token", "-t", hide_input=True, help="API token")
@click.option("--tenant-id", help="Default tenant ID")
@click.option("--mode", type=click.Choice(["raw", "gateway"]), default="raw", help="Connection mode")
@click.option("--gateway-url", help="Gateway base URL")
@click.option("--gateway-token", help="Gateway token")
@click.option("--profile", "-p", default="default", help="Profile name")
@click.option("--force", "-f", is_flag=True, help="Overwrite existing configuration")
def init_config(
    base_url: str,
    api_token: Optional[str],
    tenant_id: Optional[str],
    mode: str,
    gateway_url: Optional[str],
    gateway_token: Optional[str],
    profile: str,
    force: bool,
):
    """
    Initialize CLI configuration.

    Creates a configuration file with your API credentials. The token
    is stored securely with restricted file permissions.

    Examples:

        # Interactive setup
        hatchet config init

        # Non-interactive setup
        hatchet config init --api-token <token> --tenant-id <tenant-id>

        # Set up for a different environment
        hatchet config init --base-url https://staging.hatchet.run --profile staging
    """
    config_path = DEFAULT_CONFIG_FILE

    if config_path.exists() and not force:
        output_warning(f"Configuration file already exists at {config_path}")
        if not click.confirm("Do you want to overwrite it?"):
            click.echo("Cancelled.")
            return

    try:
        if mode == "raw" and not api_token:
            api_token = click.prompt("API token", hide_input=True)

        setup_profile(
            name=profile,
            base_url=base_url,
            api_token=api_token,
            tenant_id=tenant_id,
            gateway_url=gateway_url,
            gateway_token=gateway_token,
            mode=mode,
            set_default=True,
        )

        output_success(f"Configuration saved to {config_path}")
        click.echo(f"\nProfile '{profile}' created and set as default.")
        click.echo("\nYou can now use the CLI:")
        click.echo("  hatchet workflows list")
        click.echo("  hatchet runs list")

    except Exception as e:
        output_error(f"Failed to save configuration: {e}")
        raise SystemExit(1)


@config.command("show")
@click.option("--show-tokens", is_flag=True, help="Show API tokens (masked by default)")
def show_config(show_tokens: bool):
    """
    Show current configuration.

    Displays the current CLI configuration including profiles and settings.
    API tokens are masked by default for security.

    Examples:

        # Show config (tokens masked)
        hatchet config show

        # Show config with tokens
        hatchet config show --show-tokens
    """
    try:
        cfg = get_config()

        click.echo(f"Configuration file: {cfg.config_path}")
        click.echo(f"Default profile: {cfg.default_profile}")
        click.echo(f"Output format: {cfg.get_output_format()}")
        click.echo()

        profiles = cfg.list_profiles()
        if profiles:
            click.echo("Profiles:")
            for name, profile_data in profiles.items():
                is_default = " (default)" if name == cfg.default_profile else ""
                click.echo(f"\n  [{name}]{is_default}")
                click.echo(f"    Base URL: {profile_data.get('base_url', 'not set')}")

                token = profile_data.get("api_token", "")
                if token:
                    if show_tokens:
                        click.echo(f"    API Token: {token}")
                    else:
                        masked = token[:12] + "..." + token[-4:] if len(token) > 20 else "****"
                        click.echo(f"    API Token: {masked}")
                else:
                    click.echo("    API Token: not set")

                tenant = profile_data.get("tenant_id", "")
                if tenant:
                    click.echo(f"    Tenant ID: {tenant}")

                mode = profile_data.get("mode", "raw")
                click.echo(f"    Mode: {mode}")

                gateway_url = profile_data.get("gateway_url", "")
                if gateway_url:
                    click.echo(f"    Gateway URL: {gateway_url}")

                gateway_token = profile_data.get("gateway_token", "")
                if gateway_token:
                    if show_tokens:
                        click.echo(f"    Gateway Token: {gateway_token}")
                    else:
                        masked = gateway_token[:12] + "..." + gateway_token[-4:] if len(gateway_token) > 20 else "****"
                        click.echo(f"    Gateway Token: {masked}")
        else:
            click.echo("No profiles configured.")
            click.echo("Run 'hatchet config init' to set up your configuration.")

    except Exception as e:
        output_error(f"Failed to read configuration: {e}")
        raise SystemExit(1)


@config.command("set")
@click.argument("key")
@click.argument("value")
def set_config(key: str, value: str):
    """
    Set a configuration value.

    Updates a configuration setting. Use dot notation for nested values.

    Keys:
        default_profile  - Default profile name
        output.format    - Default output format (table, json, yaml)
        output.color     - Enable/disable color output (true, false)

    Examples:

        # Set default output format
        hatchet config set output.format json

        # Set default profile
        hatchet config set default_profile production

        # Disable color output
        hatchet config set output.color false
    """
    try:
        cfg = get_config()

        if key == "default_profile":
            profiles = cfg.list_profiles()
            if value not in profiles:
                output_error(f"Profile '{value}' does not exist.")
                click.echo(f"Available profiles: {', '.join(profiles.keys())}")
                raise SystemExit(1)
            cfg.default_profile = value

        elif key == "output.format":
            if value not in ("table", "json", "yaml"):
                output_error("Output format must be one of: table, json, yaml")
                raise SystemExit(1)
            cfg.set_output_format(value)

        elif key == "output.color":
            if value.lower() not in ("true", "false"):
                output_error("Output color must be true or false")
                raise SystemExit(1)
            cfg._config.setdefault("output", {})["color"] = value.lower() == "true"

        else:
            output_error(f"Unknown configuration key: {key}")
            click.echo("\nValid keys:")
            click.echo("  default_profile  - Default profile name")
            click.echo("  output.format    - Default output format")
            click.echo("  output.color     - Enable/disable color")
            raise SystemExit(1)

        cfg.save()
        output_success(f"Set {key} = {value}")

    except SystemExit:
        raise
    except Exception as e:
        output_error(f"Failed to update configuration: {e}")
        raise SystemExit(1)


@config.group()
def profile():
    """
    Manage configuration profiles.

    Profiles allow you to store credentials for different Hatchet
    environments (production, staging, etc.).

    Examples:

        # List profiles
        hatchet config profile list

        # Create a new profile
        hatchet config profile create staging

        # Switch default profile
        hatchet config profile use production

        # Delete a profile
        hatchet config profile delete old-profile
    """
    pass


@profile.command("list")
@click.option("--refresh", "-r", is_flag=True, help="Refresh tenant names from API")
def list_profiles(refresh: bool):
    """
    List all configuration profiles.

    Shows all configured profiles with tenant names and indicates the default.

    Examples:

        hatchet config profile list
        hatchet config profile list --refresh  # Fetch latest tenant names from API
    """
    try:
        cfg = get_config()
        profiles = cfg.list_profiles()

        if not profiles:
            click.echo("No profiles configured.")
            click.echo("Run 'hatchet config init' to create one.")
            return

        # If refresh flag, try to fetch tenant names from API
        if refresh:
            output_info("Refreshing tenant names from API...")
            for name, profile_data in profiles.items():
                tenant_id = profile_data.get("tenant_id")
                api_token = profile_data.get("api_token")
                base_url = profile_data.get("base_url")
                if tenant_id and api_token:
                    try:
                        from ..client import HatchetClient
                        client = HatchetClient(
                            base_url=base_url,
                            api_token=api_token,
                            tenant_id=tenant_id,
                        )
                        tenant_info = client.get_tenant(tenant_id)
                        tenant_name = tenant_info.get("name")
                        if tenant_name:
                            profile_data["tenant_name"] = tenant_name
                            cfg.set_profile(name, profile_data)
                    except Exception:
                        pass
            cfg.save()
            click.echo()

        # Build table data
        from rich.table import Table

        table = Table(show_header=True, header_style="bold")
        table.add_column("Profile", style="cyan")
        table.add_column("Tenant")
        table.add_column("Base URL")
        table.add_column("Default", justify="center")

        for name, profile_data in profiles.items():
            tenant_name = profile_data.get("tenant_name", "")
            tenant_id = profile_data.get("tenant_id", "")
            base_url = profile_data.get("base_url", "")
            is_default = cfg.default_profile == name

            # Display tenant name or truncated ID
            if tenant_name:
                tenant_display = tenant_name
            elif tenant_id:
                tenant_display = f"{tenant_id[:12]}..."
            else:
                tenant_display = "-"

            # Truncate base URL for display
            url_display = base_url.replace("https://", "").replace("http://", "")
            if len(url_display) > 25:
                url_display = url_display[:22] + "..."

            table.add_row(
                name,
                tenant_display,
                url_display,
                "[green]*[/green]" if is_default else "",
            )

        console.print(table)
        click.echo(f"\nUse 'hatchet use <profile>' to switch profiles.")

    except Exception as e:
        output_error(f"Failed to list profiles: {e}")
        raise SystemExit(1)


@profile.command("create")
@click.argument("name")
@click.option("--base-url", "-u", default="https://app.hatchet.run", help="Hatchet API base URL")
@click.option("--api-token", "-t", prompt=True, hide_input=True, help="API token")
@click.option("--tenant-id", help="Default tenant ID")
@click.option("--set-default", is_flag=True, help="Set as default profile")
def create_profile(
    name: str,
    base_url: str,
    api_token: str,
    tenant_id: Optional[str],
    set_default: bool,
):
    """
    Create a new configuration profile.

    Creates a profile with credentials for a Hatchet environment.
    Automatically fetches and stores the tenant name for easy identification.

    Examples:

        # Create production profile
        hatchet config profile create production

        # Create staging profile with different URL
        hatchet config profile create staging --base-url https://staging.hatchet.run

        # Create and set as default
        hatchet config profile create main --set-default
    """
    try:
        cfg = get_config()

        if name in cfg.list_profiles():
            output_warning(f"Profile '{name}' already exists.")
            if not click.confirm("Do you want to overwrite it?"):
                click.echo("Cancelled.")
                return

        # Try to fetch tenant name from the API
        tenant_name = None
        if tenant_id and api_token:
            try:
                from ..client import HatchetClient
                client = HatchetClient(
                    base_url=base_url,
                    api_token=api_token,
                    tenant_id=tenant_id,
                )
                tenant_info = client.get_tenant(tenant_id)
                tenant_name = tenant_info.get("name")
                if tenant_name:
                    output_info(f"Detected tenant: {tenant_name}")
            except Exception:
                # Silently continue if we can't fetch tenant name
                pass

        setup_profile(
            name=name,
            base_url=base_url,
            api_token=api_token,
            tenant_id=tenant_id,
            tenant_name=tenant_name,
            set_default=set_default,
        )

        output_success(f"Profile '{name}' created.")
        if set_default:
            click.echo(f"Set as default profile.")

    except Exception as e:
        output_error(f"Failed to create profile: {e}")
        raise SystemExit(1)


@profile.command("use")
@click.argument("name")
def use_profile(name: str):
    """
    Set the default profile.

    Switches the default profile used for API calls.

    Examples:

        hatchet config profile use production
    """
    try:
        cfg = get_config()

        if name not in cfg.list_profiles():
            output_error(f"Profile '{name}' does not exist.")
            profiles = cfg.list_profiles()
            if profiles:
                click.echo(f"Available profiles: {', '.join(profiles.keys())}")
            raise SystemExit(1)

        cfg.default_profile = name
        cfg.save()

        output_success(f"Default profile set to '{name}'.")

    except SystemExit:
        raise
    except Exception as e:
        output_error(f"Failed to update profile: {e}")
        raise SystemExit(1)


@profile.command("delete")
@click.argument("name")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation")
def delete_profile(name: str, yes: bool):
    """
    Delete a configuration profile.

    Removes a profile from the configuration file.

    Examples:

        hatchet config profile delete old-profile
    """
    try:
        cfg = get_config()

        if name not in cfg.list_profiles():
            output_error(f"Profile '{name}' does not exist.")
            raise SystemExit(1)

        if name == cfg.default_profile:
            output_warning("You are deleting the default profile.")

        if not yes:
            if not click.confirm(f"Are you sure you want to delete profile '{name}'?"):
                click.echo("Cancelled.")
                return

        cfg.delete_profile(name)
        cfg.save()

        output_success(f"Profile '{name}' deleted.")

        if name == cfg.default_profile:
            profiles = cfg.list_profiles()
            if profiles:
                new_default = list(profiles.keys())[0]
                cfg.default_profile = new_default
                cfg.save()
                click.echo(f"Default profile changed to '{new_default}'.")

    except SystemExit:
        raise
    except Exception as e:
        output_error(f"Failed to delete profile: {e}")
        raise SystemExit(1)
