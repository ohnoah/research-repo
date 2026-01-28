"""
Hatchet CLI Configuration - Configuration file management.

This module handles loading, saving, and managing CLI configuration,
including API credentials and default settings.

Configuration is stored in ~/.hatchet/config.yaml by default.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml


DEFAULT_CONFIG_DIR = Path.home() / ".hatchet"
DEFAULT_CONFIG_FILE = DEFAULT_CONFIG_DIR / "config.yaml"


class Config:
    """
    Configuration manager for Hatchet CLI.

    Configuration is loaded from (in order of precedence):
    1. Command-line arguments
    2. Environment variables (HATCHET_*)
    3. Configuration file (~/.hatchet/config.yaml)

    Example config.yaml:
        default_profile: production

        profiles:
          production:
            base_url: https://app.hatchet.run
            api_token: hatchet_pat_xxx
            tenant_id: tenant-uuid

          staging:
            base_url: https://staging.hatchet.run
            api_token: hatchet_pat_yyy
            tenant_id: tenant-uuid-staging

        output:
          format: table  # table, json, yaml
          color: true
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration manager.

        Args:
            config_path: Path to configuration file. Defaults to ~/.hatchet/config.yaml
        """
        self.config_path = config_path or DEFAULT_CONFIG_FILE
        self._config: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        """Load configuration from file if it exists."""
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    self._config = yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                raise ValueError(f"Invalid configuration file: {e}")
            except IOError as e:
                raise ValueError(f"Cannot read configuration file: {e}")

    def save(self) -> None:
        """Save configuration to file."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            yaml.dump(self._config, f, default_flow_style=False, sort_keys=False)
        # Set restrictive permissions (contains secrets)
        os.chmod(self.config_path, 0o600)

    @property
    def default_profile(self) -> str:
        """Get the default profile name."""
        return self._config.get("default_profile", "default")

    @default_profile.setter
    def default_profile(self, value: str) -> None:
        """Set the default profile name."""
        self._config["default_profile"] = value

    def get_profile(self, name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get a profile's configuration.

        Args:
            name: Profile name. Uses default_profile if not specified.

        Returns:
            Profile configuration dictionary
        """
        profile_name = name or self.default_profile
        profiles = self._config.get("profiles", {})
        return profiles.get(profile_name, {})

    def set_profile(self, name: str, profile_data: Dict[str, Any]) -> None:
        """
        Set a profile's configuration.

        Args:
            name: Profile name
            profile_data: Profile configuration dictionary
        """
        if "profiles" not in self._config:
            self._config["profiles"] = {}
        self._config["profiles"][name] = profile_data

    def delete_profile(self, name: str) -> bool:
        """
        Delete a profile.

        Args:
            name: Profile name to delete

        Returns:
            True if deleted, False if not found
        """
        profiles = self._config.get("profiles", {})
        if name in profiles:
            del profiles[name]
            return True
        return False

    def list_profiles(self) -> Dict[str, Dict[str, Any]]:
        """
        List all profiles.

        Returns:
            Dictionary of profile names to profile configurations
        """
        return self._config.get("profiles", {})

    def get_base_url(self, profile: Optional[str] = None) -> Optional[str]:
        """Get base URL from profile or environment."""
        env_url = os.getenv("HATCHET_BASE_URL")
        if env_url:
            return env_url
        return self.get_profile(profile).get("base_url")

    def get_api_token(self, profile: Optional[str] = None) -> Optional[str]:
        """Get API token from profile or environment."""
        env_token = os.getenv("HATCHET_API_TOKEN")
        if env_token:
            return env_token
        return self.get_profile(profile).get("api_token")

    def get_gateway_url(self, profile: Optional[str] = None) -> Optional[str]:
        """Get gateway URL from profile or environment."""
        env_url = os.getenv("GATEWAY_URL") or os.getenv("HATCHET_GATEWAY_URL")
        if env_url:
            return env_url
        return self.get_profile(profile).get("gateway_url")

    def get_gateway_token(self, profile: Optional[str] = None) -> Optional[str]:
        """Get gateway token from profile or environment."""
        env_token = os.getenv("GATEWAY_TOKEN") or os.getenv("HATCHET_GATEWAY_TOKEN")
        if env_token:
            return env_token
        return self.get_profile(profile).get("gateway_token")

    def get_mode(self, profile: Optional[str] = None) -> Optional[str]:
        """Get CLI mode from profile or environment."""
        env_mode = os.getenv("HATCHET_MODE")
        if env_mode:
            return env_mode
        return self.get_profile(profile).get("mode")

    def get_tenant_id(self, profile: Optional[str] = None) -> Optional[str]:
        """Get tenant ID from profile or environment."""
        env_tenant = os.getenv("HATCHET_TENANT_ID")
        if env_tenant:
            return env_tenant
        return self.get_profile(profile).get("tenant_id")

    def get_output_format(self) -> str:
        """Get default output format."""
        return self._config.get("output", {}).get("format", "table")

    def set_output_format(self, format: str) -> None:
        """Set default output format."""
        if "output" not in self._config:
            self._config["output"] = {}
        self._config["output"]["format"] = format

    def use_color(self) -> bool:
        """Check if color output is enabled."""
        return self._config.get("output", {}).get("color", True)


def get_config(config_path: Optional[Path] = None) -> Config:
    """
    Get or create configuration instance.

    Args:
        config_path: Optional custom config file path

    Returns:
        Configuration instance
    """
    return Config(config_path)


def setup_profile(
    name: str,
    base_url: Optional[str],
    api_token: Optional[str],
    tenant_id: Optional[str] = None,
    tenant_name: Optional[str] = None,
    gateway_url: Optional[str] = None,
    gateway_token: Optional[str] = None,
    mode: Optional[str] = None,
    set_default: bool = False,
    config_path: Optional[Path] = None,
) -> None:
    """
    Set up a new profile or update an existing one.

    Args:
        name: Profile name
        base_url: Hatchet API base URL
        api_token: API token for authentication
        tenant_id: Default tenant ID for the profile
        tenant_name: Human-readable tenant name for display
        set_default: Whether to make this the default profile
        config_path: Optional custom config file path
    """
    config = get_config(config_path)
    profile_data = {}
    if base_url:
        profile_data["base_url"] = base_url
    if api_token:
        profile_data["api_token"] = api_token
    if tenant_id:
        profile_data["tenant_id"] = tenant_id
    if tenant_name:
        profile_data["tenant_name"] = tenant_name
    if gateway_url:
        profile_data["gateway_url"] = gateway_url
    if gateway_token:
        profile_data["gateway_token"] = gateway_token
    if mode:
        profile_data["mode"] = mode

    config.set_profile(name, profile_data)

    if set_default:
        config.default_profile = name

    config.save()
