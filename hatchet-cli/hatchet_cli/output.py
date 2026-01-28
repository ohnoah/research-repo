"""
Hatchet CLI Output Formatting - Pretty output for CLI responses.

This module provides utilities for formatting API responses in various formats:
- table: Formatted tables for terminal display
- json: JSON output for scripting
- yaml: YAML output for configuration-style viewing
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional, Union

import yaml
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.tree import Tree
from rich import box

from dateutil import parser as dateparser
from dateutil.relativedelta import relativedelta


console = Console()
error_console = Console(stderr=True)


# Status colors for workflow/step runs
STATUS_COLORS = {
    "PENDING": "yellow",
    "QUEUED": "blue",
    "RUNNING": "cyan",
    "SUCCEEDED": "green",
    "FAILED": "red",
    "CANCELLED": "dim",
    "CANCELLING": "yellow",
    "PENDING_ASSIGNMENT": "yellow",
    "ASSIGNED": "blue",
}

# Worker status colors
WORKER_STATUS_COLORS = {
    "ACTIVE": "green",
    "INACTIVE": "dim",
    "PAUSED": "yellow",
}


def format_timestamp(ts: Optional[str], relative: bool = False) -> str:
    """
    Format an ISO timestamp for display.

    Args:
        ts: ISO 8601 timestamp string
        relative: If True, show relative time (e.g., "5 minutes ago")

    Returns:
        Formatted timestamp string
    """
    if not ts:
        return "-"

    try:
        dt = dateparser.parse(ts)
        if relative:
            now = datetime.now(dt.tzinfo)
            diff = relativedelta(now, dt)

            if diff.years > 0:
                return f"{diff.years}y ago"
            if diff.months > 0:
                return f"{diff.months}mo ago"
            if diff.days > 0:
                return f"{diff.days}d ago"
            if diff.hours > 0:
                return f"{diff.hours}h ago"
            if diff.minutes > 0:
                return f"{diff.minutes}m ago"
            return "just now"

        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return ts


def format_duration(start: Optional[str], end: Optional[str]) -> str:
    """
    Format the duration between two timestamps.

    Args:
        start: Start timestamp (ISO 8601)
        end: End timestamp (ISO 8601)

    Returns:
        Formatted duration string
    """
    if not start:
        return "-"

    try:
        start_dt = dateparser.parse(start)

        if end:
            end_dt = dateparser.parse(end)
        else:
            end_dt = datetime.now(start_dt.tzinfo)

        delta = end_dt - start_dt
        total_seconds = int(delta.total_seconds())

        if total_seconds < 0:
            return "-"

        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        if minutes > 0:
            return f"{minutes}m {seconds}s"
        if seconds > 0:
            return f"{seconds}s"

        # Milliseconds
        ms = int(delta.total_seconds() * 1000)
        return f"{ms}ms"
    except (ValueError, TypeError):
        return "-"


def colorize_status(status: str) -> Text:
    """
    Get colorized status text.

    Args:
        status: Status string

    Returns:
        Rich Text object with appropriate color
    """
    color = STATUS_COLORS.get(status, "white")
    return Text(status, style=color)


def truncate_id(id_str: str, length: int = 8) -> str:
    """
    Truncate an ID for display.

    Args:
        id_str: Full ID string
        length: Maximum length

    Returns:
        Truncated ID
    """
    if not id_str:
        return "-"
    if len(id_str) <= length:
        return id_str
    return id_str[:length] + "..."


def output_json(data: Any) -> None:
    """
    Output data as formatted JSON.

    Args:
        data: Data to output
    """
    print(json.dumps(data, indent=2, default=str))


def output_yaml(data: Any) -> None:
    """
    Output data as YAML.

    Args:
        data: Data to output
    """
    print(yaml.dump(data, default_flow_style=False, sort_keys=False))


def output_table(
    data: List[Dict[str, Any]],
    columns: List[tuple],
    title: Optional[str] = None,
    show_row_numbers: bool = False,
) -> None:
    """
    Output data as a formatted table.

    Args:
        data: List of dictionaries to display
        columns: List of (key, header, formatter) tuples
        title: Optional table title
        show_row_numbers: Whether to show row numbers
    """
    table = Table(
        title=title,
        box=box.ROUNDED,
        show_header=True,
        header_style="bold",
    )

    if show_row_numbers:
        table.add_column("#", style="dim")

    for col in columns:
        header = col[1] if len(col) > 1 else col[0]
        table.add_column(header)

    for idx, row in enumerate(data, 1):
        row_values = []
        if show_row_numbers:
            row_values.append(str(idx))

        for col in columns:
            key = col[0]
            formatter = col[2] if len(col) > 2 else None

            # Handle nested keys with dot notation
            value = row
            for k in key.split("."):
                if isinstance(value, dict):
                    value = value.get(k, "")
                else:
                    value = ""
                    break

            if formatter:
                value = formatter(value)
            elif value is None:
                value = "-"
            elif not isinstance(value, str):
                value = str(value)

            row_values.append(value)

        table.add_row(*row_values)

    console.print(table)


def output_detail(
    data: Dict[str, Any],
    fields: List[tuple],
    title: Optional[str] = None,
) -> None:
    """
    Output detailed view of a single item.

    Args:
        data: Dictionary to display
        fields: List of (key, label, formatter) tuples
        title: Optional panel title
    """
    lines = []

    for field in fields:
        key = field[0]
        label = field[1] if len(field) > 1 else key
        formatter = field[2] if len(field) > 2 else None

        # Handle nested keys
        value = data
        for k in key.split("."):
            if isinstance(value, dict):
                value = value.get(k, "")
            else:
                value = ""
                break

        if formatter:
            value = formatter(value)
        elif value is None:
            value = "-"
        elif isinstance(value, (dict, list)):
            value = json.dumps(value, indent=2)
        else:
            value = str(value)

        lines.append(f"[bold]{label}:[/bold] {value}")

    content = "\n".join(lines)

    if title:
        console.print(Panel(content, title=title, expand=False))
    else:
        console.print(content)


def output_tree(
    data: Dict[str, Any],
    title: str = "Data",
) -> None:
    """
    Output data as a tree structure.

    Args:
        data: Dictionary to display as tree
        title: Root title
    """
    tree = Tree(f"[bold]{title}[/bold]")
    _add_tree_nodes(tree, data)
    console.print(tree)


def _add_tree_nodes(tree: Tree, data: Any) -> None:
    """Recursively add nodes to a tree."""
    if isinstance(data, dict):
        for key, value in data.items():
            if isinstance(value, (dict, list)):
                branch = tree.add(f"[bold]{key}[/bold]")
                _add_tree_nodes(branch, value)
            else:
                tree.add(f"[bold]{key}:[/bold] {value}")
    elif isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, (dict, list)):
                branch = tree.add(f"[dim][{i}][/dim]")
                _add_tree_nodes(branch, item)
            else:
                tree.add(f"[dim][{i}][/dim] {item}")


def output_error(message: str, hint: Optional[str] = None) -> None:
    """
    Output an error message.

    Args:
        message: Error message
        hint: Optional hint for resolution
    """
    error_console.print(f"[red]Error:[/red] {message}")
    if hint:
        error_console.print(f"[dim]Hint: {hint}[/dim]")


def output_success(message: str) -> None:
    """
    Output a success message.

    Args:
        message: Success message
    """
    console.print(f"[green]{message}[/green]")


def output_warning(message: str) -> None:
    """
    Output a warning message.

    Args:
        message: Warning message
    """
    console.print(f"[yellow]Warning:[/yellow] {message}")


def output_info(message: str) -> None:
    """
    Output an informational message.

    Args:
        message: Info message
    """
    console.print(f"[blue]{message}[/blue]")


def confirm(message: str, default: bool = False) -> bool:
    """
    Prompt for confirmation.

    Args:
        message: Confirmation prompt
        default: Default response if user just presses enter

    Returns:
        True if confirmed, False otherwise
    """
    suffix = " [Y/n]" if default else " [y/N]"
    response = console.input(f"{message}{suffix} ").strip().lower()

    if not response:
        return default

    return response in ("y", "yes")


class OutputFormatter:
    """
    Centralized output formatter that handles different output modes.

    Usage:
        formatter = OutputFormatter(format="json")
        formatter.output(data)
    """

    def __init__(self, format: str = "table"):
        """
        Initialize formatter.

        Args:
            format: Output format (table, json, yaml)
        """
        self.format = format

    def output(
        self,
        data: Any,
        columns: Optional[List[tuple]] = None,
        fields: Optional[List[tuple]] = None,
        title: Optional[str] = None,
    ) -> None:
        """
        Output data in the configured format.

        Args:
            data: Data to output
            columns: Column definitions for table format (list items)
            fields: Field definitions for detail view (single items)
            title: Optional title
        """
        if self.format == "json":
            output_json(data)
        elif self.format == "yaml":
            output_yaml(data)
        else:
            # Table format
            if isinstance(data, list) and columns:
                output_table(data, columns, title=title)
            elif isinstance(data, dict) and fields:
                output_detail(data, fields, title=title)
            else:
                # Fallback to JSON for complex data
                output_json(data)


def paginate_output(
    data: List[Any],
    page: int = 1,
    per_page: int = 20,
) -> tuple:
    """
    Paginate a list of items.

    Args:
        data: List of items
        page: Current page (1-indexed)
        per_page: Items per page

    Returns:
        Tuple of (page_items, total_pages, current_page)
    """
    total = len(data)
    total_pages = (total + per_page - 1) // per_page
    start_idx = (page - 1) * per_page
    end_idx = start_idx + per_page

    return data[start_idx:end_idx], total_pages, page
