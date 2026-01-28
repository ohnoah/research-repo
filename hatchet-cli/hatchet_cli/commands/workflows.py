"""
Workflow Commands - Manage workflows in Hatchet.

Commands:
    list    - List all workflows
    get     - Get workflow details
    trigger - Trigger a workflow run
    metrics - Get workflow metrics
    workers - Get worker count for workflow
    delete  - Delete a workflow
"""

import json
from typing import Optional

import click

from ..client import HatchetClient
from ..exceptions import HatchetAPIError, HatchetConfigurationError
from ..output import (
    OutputFormatter,
    colorize_status,
    format_timestamp,
    output_error,
    output_success,
    output_table,
    output_detail,
    output_json,
    confirm,
)


@click.group()
def workflows():
    """
    Manage workflows.

    Workflows define the structure and steps of your background tasks.
    Use these commands to list, view, trigger, and manage workflows.

    Examples:

        # List all workflows
        hatchet workflows list

        # Get details of a specific workflow
        hatchet workflows get my-workflow

        # Trigger a workflow with input
        hatchet workflows trigger my-workflow --input '{"key": "value"}'

        # Get workflow metrics
        hatchet workflows metrics my-workflow
    """
    pass


@workflows.command("list")
@click.option("--limit", "-l", default=50, help="Maximum number of workflows to return")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def list_workflows(ctx, limit: int, output_format: str):
    """
    List all workflows.

    Shows all workflows registered in your Hatchet tenant, including their
    names, versions, and trigger configurations.

    Examples:

        # List workflows as table
        hatchet workflows list

        # List as JSON for scripting
        hatchet workflows list --format json

        # Limit results
        hatchet workflows list --limit 10
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.list_workflows()

        workflows_list = result.get("rows", [])

        if not workflows_list:
            click.echo("No workflows found.")
            return

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            columns = [
                ("name", "Name"),
                ("metadata.id", "ID", lambda x: x[:12] + "..." if x and len(x) > 12 else x),
                ("versions", "Versions", lambda v: str(len(v)) if v else "0"),
                ("isPaused", "Paused", lambda x: "Yes" if x else "No"),
            ]
            output_table(workflows_list, columns, title=f"Workflows ({len(workflows_list)} total)")
        else:
            formatter.output(workflows_list)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@workflows.command("get")
@click.argument("workflow_id")
@click.option("--version", "-v", help="Specific version to retrieve")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def get_workflow(ctx, workflow_id: str, version: Optional[str], output_format: str):
    """
    Get workflow details.

    Retrieves detailed information about a workflow, including its steps,
    triggers, concurrency settings, and version history.

    WORKFLOW_ID can be the workflow name or UUID.

    Examples:

        # Get workflow by name
        hatchet workflows get my-workflow

        # Get specific version
        hatchet workflows get my-workflow --version v1.0.0

        # Get as JSON
        hatchet workflows get my-workflow --format json
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        workflow = client.get_workflow(workflow_id)

        if version:
            version_data = client.get_workflow_version(workflow_id, version)
            workflow["selectedVersion"] = version_data

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            fields = [
                ("name", "Name"),
                ("metadata.id", "ID"),
                ("description", "Description"),
                ("isPaused", "Paused", lambda x: "Yes" if x else "No"),
                ("metadata.createdAt", "Created", lambda x: format_timestamp(x)),
                ("metadata.updatedAt", "Updated", lambda x: format_timestamp(x)),
            ]
            output_detail(workflow, fields, title=f"Workflow: {workflow.get('name', workflow_id)}")

            # Show versions if available
            versions = workflow.get("versions", [])
            if versions:
                click.echo("\nVersions:")
                version_cols = [
                    ("version", "Version"),
                    ("metadata.id", "ID", lambda x: x[:12] + "..." if x else "-"),
                    ("metadata.createdAt", "Created", lambda x: format_timestamp(x)),
                ]
                output_table(versions, version_cols)

            # Show jobs/steps if selected version available
            if "selectedVersion" in workflow:
                sv = workflow["selectedVersion"]
                jobs = sv.get("jobs", [])
                if jobs:
                    click.echo("\nSteps:")
                    for job in jobs:
                        click.echo(f"  Job: {job.get('name', 'unnamed')}")
                        for step in job.get("steps", []):
                            click.echo(f"    - {step.get('readableId', step.get('id', 'unnamed'))}")
        else:
            formatter.output(workflow)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@workflows.command("trigger")
@click.argument("workflow_id")
@click.option("--input", "-i", "input_data", help="Input data as JSON string")
@click.option("--input-file", type=click.Path(exists=True), help="Path to JSON file with input data")
@click.option("--metadata", "-m", multiple=True, help="Additional metadata (key=value format)")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def trigger_workflow(
    ctx,
    workflow_id: str,
    input_data: Optional[str],
    input_file: Optional[str],
    metadata: tuple,
    output_format: str,
):
    """
    Trigger a workflow run.

    Starts a new execution of the specified workflow. You can provide
    input data as a JSON string or from a file.

    WORKFLOW_ID can be the workflow name or UUID.

    Examples:

        # Trigger with inline JSON input
        hatchet workflows trigger my-workflow --input '{"userId": "123"}'

        # Trigger with input from file
        hatchet workflows trigger my-workflow --input-file ./input.json

        # Trigger with metadata
        hatchet workflows trigger my-workflow -m env=production -m priority=high

        # Trigger without input
        hatchet workflows trigger my-workflow
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
                key, value = m.split("=", 1)
                additional_metadata[key] = value
            else:
                output_error(f"Invalid metadata format: {m}. Use key=value format.")
                raise SystemExit(1)

        result = client.trigger_workflow(
            workflow_id,
            input_data=parsed_input,
            additional_metadata=additional_metadata if additional_metadata else None,
        )

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            workflow_run_id = result.get("workflowRunId", result.get("id", "unknown"))
            output_success(f"Workflow triggered successfully!")
            click.echo(f"Workflow Run ID: {workflow_run_id}")
        else:
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@workflows.command("metrics")
@click.argument("workflow_id")
@click.option("--status", "-s", help="Filter by status")
@click.option("--group-key", "-g", help="Group key for aggregation")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def workflow_metrics(
    ctx,
    workflow_id: str,
    status: Optional[str],
    group_key: Optional[str],
    output_format: str,
):
    """
    Get workflow execution metrics.

    Shows aggregated statistics about workflow runs including counts
    by status, average duration, and error rates.

    WORKFLOW_ID can be the workflow name or UUID.

    Examples:

        # Get all metrics
        hatchet workflows metrics my-workflow

        # Filter by status
        hatchet workflows metrics my-workflow --status FAILED

        # Group by key
        hatchet workflows metrics my-workflow --group-key region
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.get_workflow_metrics(workflow_id, status=status, group_key=group_key)

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            click.echo(f"Metrics for workflow: {workflow_id}")
            click.echo()
            if isinstance(result, dict):
                for key, value in result.items():
                    if isinstance(value, list):
                        click.echo(f"{key}:")
                        for item in value:
                            click.echo(f"  - {item}")
                    else:
                        click.echo(f"{key}: {value}")
            else:
                output_json(result)
        else:
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@workflows.command("workers")
@click.argument("workflow_id")
@click.option("--format", "-f", "output_format", type=click.Choice(["table", "json", "yaml"]), default="table", help="Output format")
@click.pass_context
def workflow_workers(ctx, workflow_id: str, output_format: str):
    """
    Get worker count for a workflow.

    Shows how many workers are available to process runs of this workflow.

    WORKFLOW_ID can be the workflow name or UUID.

    Examples:

        hatchet workflows workers my-workflow
    """
    try:
        client: HatchetClient = ctx.obj["client"]
        result = client.get_workflow_worker_count(workflow_id)

        formatter = OutputFormatter(output_format)

        if output_format == "table":
            count = result.get("count", result.get("workerCount", 0))
            click.echo(f"Workers for workflow '{workflow_id}': {count}")
        else:
            formatter.output(result)

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)


@workflows.command("delete")
@click.argument("workflow_id")
@click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
@click.pass_context
def delete_workflow(ctx, workflow_id: str, yes: bool):
    """
    Delete a workflow.

    Permanently removes a workflow and all its versions. This action cannot
    be undone. Running workflow runs will be cancelled.

    WORKFLOW_ID can be the workflow name or UUID.

    Examples:

        # Delete with confirmation
        hatchet workflows delete my-workflow

        # Delete without confirmation
        hatchet workflows delete my-workflow --yes
    """
    try:
        if not yes:
            if not confirm(f"Are you sure you want to delete workflow '{workflow_id}'?"):
                click.echo("Cancelled.")
                return

        client: HatchetClient = ctx.obj["client"]
        client.delete_workflow(workflow_id)
        output_success(f"Workflow '{workflow_id}' deleted successfully.")

    except HatchetConfigurationError as e:
        output_error(str(e))
        raise SystemExit(1)
    except HatchetAPIError as e:
        output_error(str(e))
        raise SystemExit(1)
