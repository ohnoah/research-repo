"""
Hatchet API Client - Core HTTP client for interacting with Hatchet REST API.

This module provides the HatchetClient class which handles:
- Authentication via API tokens
- Request/response handling
- Error handling and retries
- Base URL configuration
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urljoin

import httpx

from .exceptions import (
    HatchetAPIError,
    HatchetAuthenticationError,
    HatchetConfigurationError,
    HatchetNotFoundError,
    HatchetRateLimitError,
)


class HatchetClient:
    """
    HTTP client for Hatchet REST API.

    The client handles authentication, request building, and response parsing
    for all Hatchet API endpoints.

    Attributes:
        base_url: The base URL of the Hatchet API server
        api_token: The API token for authentication
        tenant_id: The default tenant ID for scoped operations

    Example:
        >>> client = HatchetClient(
        ...     base_url="https://app.hatchet.run",
        ...     api_token="hatchet_pat_...",
        ...     tenant_id="tenant-uuid"
        ... )
        >>> workflows = client.list_workflows()
    """

    DEFAULT_TIMEOUT = 30.0
    DEFAULT_BASE_URL = "https://app.hatchet.run"

    def __init__(
        self,
        base_url: Optional[str] = None,
        api_token: Optional[str] = None,
        tenant_id: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize the Hatchet API client.

        Args:
            base_url: The base URL of the Hatchet API. Defaults to https://app.hatchet.run
            api_token: The API token for authentication. Can also be set via HATCHET_API_TOKEN
            tenant_id: The default tenant ID. Can also be set via HATCHET_TENANT_ID
            timeout: Request timeout in seconds

        Raises:
            HatchetConfigurationError: If no API token is provided
        """
        self.base_url = (base_url or os.getenv("HATCHET_BASE_URL", self.DEFAULT_BASE_URL)).rstrip(
            "/"
        )
        self.api_token = api_token or os.getenv("HATCHET_API_TOKEN")
        self.tenant_id = tenant_id or os.getenv("HATCHET_TENANT_ID")
        self.timeout = timeout

        if not self.api_token:
            raise HatchetConfigurationError(
                "API token is required. Set via --api-token, HATCHET_API_TOKEN environment "
                "variable, or in ~/.hatchet/config.yaml"
            )

        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers=self._build_headers(),
        )

    def _build_headers(self) -> Dict[str, str]:
        """Build default headers for API requests."""
        return {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "hatchet-cli/1.0.0",
        }

    def _handle_response(self, response: httpx.Response) -> Any:
        """
        Handle API response and raise appropriate exceptions.

        Args:
            response: The HTTP response object

        Returns:
            Parsed JSON response data

        Raises:
            HatchetAuthenticationError: For 401 responses
            HatchetNotFoundError: For 404 responses
            HatchetRateLimitError: For 429 responses
            HatchetAPIError: For other error responses
        """
        if response.status_code == 204:
            return None

        try:
            data = response.json() if response.content else {}
        except json.JSONDecodeError:
            data = {"message": response.text}

        # Ensure data is a dict for .get() calls
        if data is None:
            data = {}

        if response.status_code == 401:
            raise HatchetAuthenticationError(
                data.get("message", "Authentication failed. Check your API token.")
            )

        if response.status_code == 403:
            raise HatchetAuthenticationError(
                data.get("message", "Access forbidden. Check your permissions.")
            )

        if response.status_code == 404:
            raise HatchetNotFoundError(data.get("message", "Resource not found."))

        if response.status_code == 429:
            raise HatchetRateLimitError(
                data.get("message", "Rate limit exceeded. Please wait before retrying.")
            )

        if response.status_code >= 400:
            error_msg = data.get("message", f"API request failed with status {response.status_code}")
            raise HatchetAPIError(error_msg, status_code=response.status_code)

        return data

    def _request(
        self,
        method: str,
        path: str,
        params: Optional[Dict[str, Any]] = None,
        json_data: Optional[Dict[str, Any]] = None,
    ) -> Any:
        """
        Make an HTTP request to the Hatchet API.

        Args:
            method: HTTP method (GET, POST, PATCH, DELETE)
            path: API endpoint path
            params: Query parameters
            json_data: JSON request body

        Returns:
            Parsed response data
        """
        # Filter out None values from params
        if params:
            params = {k: v for k, v in params.items() if v is not None}

        response = self._client.request(
            method=method,
            url=path,
            params=params,
            json=json_data,
        )
        return self._handle_response(response)

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        """Make a GET request."""
        return self._request("GET", path, params=params)

    def _post(
        self, path: str, json_data: Optional[Dict[str, Any]] = None, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Make a POST request."""
        return self._request("POST", path, params=params, json_data=json_data)

    def _patch(self, path: str, json_data: Optional[Dict[str, Any]] = None) -> Any:
        """Make a PATCH request."""
        return self._request("PATCH", path, json_data=json_data)

    def _delete(self, path: str) -> Any:
        """Make a DELETE request."""
        return self._request("DELETE", path)

    def _require_tenant(self, tenant_id: Optional[str] = None) -> str:
        """Get tenant ID or raise if not configured."""
        tid = tenant_id or self.tenant_id
        if not tid:
            raise HatchetConfigurationError(
                "Tenant ID is required. Set via --tenant, HATCHET_TENANT_ID environment "
                "variable, or in ~/.hatchet/config.yaml"
            )
        return tid

    # =========================================================================
    # User & Authentication
    # =========================================================================

    def get_current_user(self) -> Dict[str, Any]:
        """
        Get the current authenticated user's information.

        Returns:
            User data including email, name, and tenant memberships
        """
        return self._get("/api/v1/users/current")

    def list_memberships(self) -> Dict[str, Any]:
        """
        List all tenant memberships for the current user.

        Returns:
            List of tenant memberships with roles
        """
        return self._get("/api/v1/users/memberships")

    # =========================================================================
    # Tenants
    # =========================================================================

    def get_tenant(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get tenant details.

        Args:
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            Tenant information including name, slug, and settings
        """
        tid = self._require_tenant(tenant_id)
        return self._get(f"/api/v1/tenants/{tid}")

    def list_tenant_members(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        List all members of a tenant.

        Args:
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            List of tenant members with their roles
        """
        tid = self._require_tenant(tenant_id)
        return self._get(f"/api/v1/tenants/{tid}/members")

    def get_queue_metrics(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get queue metrics for the tenant.

        Args:
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            Queue metrics including pending, running, and completed counts
        """
        tid = self._require_tenant(tenant_id)
        return self._get(f"/api/v1/tenants/{tid}/queue-metrics")

    def get_task_stats(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get task statistics for the tenant.

        Args:
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            Task statistics
        """
        tid = self._require_tenant(tenant_id)
        return self._get(f"/api/v1/tenants/{tid}/task-stats")

    # =========================================================================
    # API Tokens
    # =========================================================================

    def list_api_tokens(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        List all API tokens for the tenant.

        Args:
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            List of API tokens (tokens are masked)
        """
        tid = self._require_tenant(tenant_id)
        return self._get(f"/api/v1/tenants/{tid}/api-tokens")

    def create_api_token(
        self, name: str, expires_in: Optional[str] = None, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Create a new API token.

        Args:
            name: Name/description for the token
            expires_in: Expiration duration (e.g., "30d", "1y")
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            The created token (only shown once)
        """
        tid = self._require_tenant(tenant_id)
        data = {"name": name}
        if expires_in:
            data["expiresIn"] = expires_in
        return self._post(f"/api/v1/tenants/{tid}/api-tokens", json_data=data)

    def revoke_api_token(self, token_id: str) -> None:
        """
        Revoke an API token.

        Args:
            token_id: The token ID to revoke
        """
        self._post(f"/api/v1/api-tokens/{token_id}")

    # =========================================================================
    # Workflows
    # =========================================================================

    def list_workflows(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        List all workflows for the tenant.

        Args:
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            Paginated list of workflows with versions
        """
        tid = self._require_tenant(tenant_id)
        return self._get(f"/api/v1/tenants/{tid}/workflows")

    def get_workflow(self, workflow_id: str) -> Dict[str, Any]:
        """
        Get workflow details.

        Args:
            workflow_id: The workflow ID or name

        Returns:
            Workflow details including versions and configuration
        """
        return self._get(f"/api/v1/workflows/{workflow_id}")

    def get_workflow_version(
        self, workflow_id: str, version: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get a specific workflow version.

        Args:
            workflow_id: The workflow ID
            version: The version string. Gets latest if not provided.

        Returns:
            Workflow version details including steps and triggers
        """
        params = {"version": version} if version else None
        return self._get(f"/api/v1/workflows/{workflow_id}/versions", params=params)

    def trigger_workflow(
        self,
        workflow_id: str,
        input_data: Optional[Dict[str, Any]] = None,
        additional_metadata: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        """
        Trigger a workflow run.

        Args:
            workflow_id: The workflow ID or name
            input_data: Input data for the workflow
            additional_metadata: Additional metadata key-value pairs

        Returns:
            The created workflow run
        """
        data = {}
        if input_data:
            data["input"] = input_data
        if additional_metadata:
            data["additionalMetadata"] = additional_metadata
        return self._post(f"/api/v1/workflows/{workflow_id}/trigger", json_data=data)

    def get_workflow_metrics(
        self,
        workflow_id: str,
        status: Optional[str] = None,
        group_key: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Get workflow metrics.

        Args:
            workflow_id: The workflow ID
            status: Filter by status
            group_key: Group key for aggregation

        Returns:
            Workflow execution metrics
        """
        params = {"status": status, "groupKey": group_key}
        return self._get(f"/api/v1/workflows/{workflow_id}/metrics", params=params)

    def get_workflow_worker_count(
        self, workflow_id: str, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get the number of workers available for a workflow.

        Args:
            workflow_id: The workflow ID
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            Worker count information
        """
        tid = self._require_tenant(tenant_id)
        return self._get(f"/api/v1/tenants/{tid}/workflows/{workflow_id}/worker-count")

    def delete_workflow(self, workflow_id: str) -> None:
        """
        Delete a workflow.

        Args:
            workflow_id: The workflow ID to delete
        """
        self._delete(f"/api/v1/workflows/{workflow_id}")

    # =========================================================================
    # Workflow Runs
    # =========================================================================

    def list_workflow_runs(
        self,
        tenant_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
        workflow_id: Optional[str] = None,
        event_id: Optional[str] = None,
        parent_workflow_run_id: Optional[str] = None,
        parent_step_run_id: Optional[str] = None,
        statuses: Optional[List[str]] = None,
        kinds: Optional[List[str]] = None,
        additional_metadata: Optional[List[str]] = None,
        created_after: Optional[str] = None,
        created_before: Optional[str] = None,
        finished_after: Optional[str] = None,
        finished_before: Optional[str] = None,
        order_by_field: Optional[str] = None,
        order_by_direction: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List workflow runs with filtering options.

        Args:
            tenant_id: The tenant ID. Uses default if not provided.
            offset: Pagination offset
            limit: Number of results to return (max 50)
            workflow_id: Filter by workflow ID
            event_id: Filter by triggering event ID
            parent_workflow_run_id: Filter by parent workflow run
            parent_step_run_id: Filter by parent step run
            statuses: Filter by status(es): PENDING, QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED
            kinds: Filter by kind(s): DEFAULT, SCHEDULED, CRON, CHILD, EVENT
            additional_metadata: Filter by metadata (format: key:value)
            created_after: Filter runs created after this timestamp (ISO 8601)
            created_before: Filter runs created before this timestamp (ISO 8601)
            finished_after: Filter runs finished after this timestamp (ISO 8601)
            finished_before: Filter runs finished before this timestamp (ISO 8601)
            order_by_field: Field to order by (createdAt, finishedAt)
            order_by_direction: Order direction (ASC, DESC)

        Returns:
            Paginated list of workflow runs
        """
        tid = self._require_tenant(tenant_id)
        params = {
            "offset": offset,
            "limit": min(limit, 50),
            "workflowId": workflow_id,
            "eventId": event_id,
            "parentWorkflowRunId": parent_workflow_run_id,
            "parentStepRunId": parent_step_run_id,
            "createdAfter": created_after,
            "createdBefore": created_before,
            "finishedAfter": finished_after,
            "finishedBefore": finished_before,
            "orderByField": order_by_field,
            "orderByDirection": order_by_direction,
        }
        if statuses:
            params["statuses"] = statuses
        if kinds:
            params["kinds"] = kinds
        if additional_metadata:
            params["additionalMetadata"] = additional_metadata

        # Use stable API which requires 'since' and 'only_tasks' parameters
        from datetime import datetime, timedelta, timezone
        if not params.get("since"):
            # Default to last 7 days if no since provided
            default_since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
            params["since"] = created_after or default_since
        else:
            params["since"] = params.get("since") or created_after
        params["only_tasks"] = "false"
        # Map old parameter names to new API
        if created_after:
            params["since"] = created_after
        if created_before:
            params["until"] = created_before
        # Clean up old params not in stable API
        params.pop("createdAfter", None)
        params.pop("createdBefore", None)
        params.pop("finishedAfter", None)
        params.pop("finishedBefore", None)
        params.pop("orderByField", None)
        params.pop("orderByDirection", None)
        params.pop("workflowId", None)
        if workflow_id:
            params["workflow_ids"] = [workflow_id]

        return self._get(f"/api/v1/stable/tenants/{tid}/workflow-runs", params=params)

    def get_workflow_run(self, workflow_run_id: str) -> Dict[str, Any]:
        """
        Get workflow run details.

        Args:
            workflow_run_id: The workflow run ID

        Returns:
            Detailed workflow run information including steps
        """
        return self._get(f"/api/v1/stable/workflow-runs/{workflow_run_id}")

    def get_workflow_run_status(self, workflow_run_id: str) -> Dict[str, Any]:
        """
        Get workflow run status.

        Args:
            workflow_run_id: The workflow run ID

        Returns:
            Workflow run status
        """
        return self._get(f"/api/v1/stable/workflow-runs/{workflow_run_id}/status")

    def get_workflow_run_input(
        self, workflow_run_id: str, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get the input data for a workflow run.

        Args:
            workflow_run_id: The workflow run ID
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            The input data passed to the workflow
        """
        tid = self._require_tenant(tenant_id)
        return self._get(f"/api/v1/tenants/{tid}/workflows/runs/{workflow_run_id}/input")

    def get_workflow_run_shape(
        self, workflow_run_id: str, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get the DAG shape of a workflow run.

        Args:
            workflow_run_id: The workflow run ID
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            The workflow run DAG structure
        """
        tid = self._require_tenant(tenant_id)
        return self._get(f"/api/v1/tenants/{tid}/workflows/runs/{workflow_run_id}/shape")

    def get_task_events(self, workflow_run_id: str) -> Dict[str, Any]:
        """
        Get task events for a workflow run.

        Args:
            workflow_run_id: The workflow run ID

        Returns:
            List of task events
        """
        return self._get(f"/api/v1/stable/workflow-runs/{workflow_run_id}/task-events")

    def get_task_timings(self, workflow_run_id: str) -> Dict[str, Any]:
        """
        Get task timing information for a workflow run.

        Args:
            workflow_run_id: The workflow run ID

        Returns:
            Task timing data
        """
        return self._get(f"/api/v1/stable/workflow-runs/{workflow_run_id}/task-timings")

    def cancel_workflow_runs(
        self,
        workflow_run_ids: List[str],
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Cancel one or more workflow runs.

        Args:
            workflow_run_ids: List of workflow run IDs to cancel
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            Cancellation result
        """
        tid = self._require_tenant(tenant_id)
        return self._post(
            f"/api/v1/tenants/{tid}/workflows/cancel",
            json_data={"workflowRunIds": workflow_run_ids},
        )

    def replay_workflow_runs(
        self,
        workflow_run_ids: List[str],
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Replay one or more workflow runs.

        Args:
            workflow_run_ids: List of workflow run IDs to replay
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            Replay result with new workflow run IDs
        """
        tid = self._require_tenant(tenant_id)
        return self._post(
            f"/api/v1/tenants/{tid}/workflows/runs/replay",
            json_data={"workflowRunIds": workflow_run_ids},
        )

    def get_workflow_run_metrics(
        self,
        tenant_id: Optional[str] = None,
        workflow_id: Optional[str] = None,
        parent_workflow_run_id: Optional[str] = None,
        parent_step_run_id: Optional[str] = None,
        event_id: Optional[str] = None,
        additional_metadata: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Get aggregated workflow run metrics.

        Args:
            tenant_id: The tenant ID. Uses default if not provided.
            workflow_id: Filter by workflow ID
            parent_workflow_run_id: Filter by parent workflow run
            parent_step_run_id: Filter by parent step run
            event_id: Filter by event ID
            additional_metadata: Filter by metadata (format: key:value)

        Returns:
            Aggregated metrics (counts by status, etc.)
        """
        tid = self._require_tenant(tenant_id)
        params = {
            "workflowId": workflow_id,
            "parentWorkflowRunId": parent_workflow_run_id,
            "parentStepRunId": parent_step_run_id,
            "eventId": event_id,
        }
        if additional_metadata:
            params["additionalMetadata"] = additional_metadata
        return self._get(f"/api/v1/tenants/{tid}/workflows/runs/metrics", params=params)

    def list_child_runs(
        self,
        parent_run_id: str,
        tenant_id: Optional[str] = None,
        limit: int = 50,
    ) -> Dict[str, Any]:
        """
        List child workflow runs spawned by a parent run.

        Args:
            parent_run_id: The parent workflow run ID
            tenant_id: The tenant ID. Uses default if not provided.
            limit: Maximum number of child runs to return

        Returns:
            List of child workflow runs
        """
        tid = self._require_tenant(tenant_id)
        from datetime import datetime, timedelta, timezone
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()
        return self._get(
            f"/api/v1/stable/tenants/{tid}/workflow-runs",
            params={
                "parent_task_external_id": parent_run_id,
                "limit": limit,
                "since": since,
                "only_tasks": "false",
            },
        )

    def list_runs_in_timewindow(
        self,
        since: str,
        until: Optional[str] = None,
        tenant_id: Optional[str] = None,
        limit: int = 100,
    ) -> Dict[str, Any]:
        """
        List workflow runs within a time window.

        This is an efficient way to find all runs created during a specific
        time period, which can then be filtered client-side by parentTaskExternalId.

        Args:
            since: Start of time window (ISO 8601 timestamp)
            until: End of time window (ISO 8601 timestamp), defaults to now
            tenant_id: The tenant ID. Uses default if not provided.
            limit: Maximum number of runs to return

        Returns:
            List of workflow runs in the time window
        """
        tid = self._require_tenant(tenant_id)
        params = {
            "limit": limit,
            "since": since,
            "only_tasks": "false",
        }
        if until:
            params["until"] = until
        return self._get(
            f"/api/v1/stable/tenants/{tid}/workflow-runs",
            params=params,
        )

    # =========================================================================
    # Step Runs
    # =========================================================================

    def get_step_run(self, step_run_id: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get step run details.

        Args:
            step_run_id: The step run ID
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            Detailed step run information
        """
        tid = self._require_tenant(tenant_id)
        return self._get(f"/api/v1/tenants/{tid}/step-runs/{step_run_id}")

    def get_step_run_logs(
        self, step_run_id: str, offset: int = 0, limit: int = 100
    ) -> Dict[str, Any]:
        """
        Get logs for a step run.

        Args:
            step_run_id: The step run ID
            offset: Pagination offset
            limit: Number of log entries to return

        Returns:
            Step run logs
        """
        return self._get(
            f"/api/v1/stable/tasks/{step_run_id}/logs",
            params={"offset": offset, "limit": limit},
        )

    def get_step_run_events(self, step_run_id: str) -> Dict[str, Any]:
        """
        Get events for a step run.

        Args:
            step_run_id: The step run ID

        Returns:
            Step run events
        """
        return self._get(f"/api/v1/step-runs/{step_run_id}/events")

    def get_step_run_archives(self, step_run_id: str) -> Dict[str, Any]:
        """
        Get archives/history for a step run.

        Args:
            step_run_id: The step run ID

        Returns:
            Step run archives (retry history)
        """
        return self._get(f"/api/v1/step-runs/{step_run_id}/archives")

    def get_step_run_schema(
        self, step_run_id: str, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get input/output schema for a step run.

        Args:
            step_run_id: The step run ID
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            Step run input and output schemas
        """
        tid = self._require_tenant(tenant_id)
        return self._get(f"/api/v1/tenants/{tid}/step-runs/{step_run_id}/schema")

    def rerun_step(self, step_run_id: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Rerun a step.

        Args:
            step_run_id: The step run ID
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            New step run information
        """
        tid = self._require_tenant(tenant_id)
        return self._post(f"/api/v1/tenants/{tid}/step-runs/{step_run_id}/rerun")

    def cancel_step_run(self, step_run_id: str, tenant_id: Optional[str] = None) -> None:
        """
        Cancel a step run.

        Args:
            step_run_id: The step run ID
            tenant_id: The tenant ID. Uses default if not provided.
        """
        tid = self._require_tenant(tenant_id)
        self._post(f"/api/v1/tenants/{tid}/step-runs/{step_run_id}/cancel")

    # =========================================================================
    # Events
    # =========================================================================

    def list_events(
        self,
        tenant_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
        keys: Optional[List[str]] = None,
        workflows: Optional[List[str]] = None,
        statuses: Optional[List[str]] = None,
        search: Optional[str] = None,
        order_by_field: Optional[str] = None,
        order_by_direction: Optional[str] = None,
        additional_metadata: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        List events with filtering.

        Args:
            tenant_id: The tenant ID. Uses default if not provided.
            offset: Pagination offset
            limit: Number of results to return
            keys: Filter by event key(s)
            workflows: Filter by workflow ID(s)
            statuses: Filter by status(es)
            search: Search term
            order_by_field: Field to order by
            order_by_direction: Order direction (ASC, DESC)
            additional_metadata: Filter by metadata (format: key:value)

        Returns:
            Paginated list of events
        """
        tid = self._require_tenant(tenant_id)
        params = {
            "offset": offset,
            "limit": min(limit, 50),
            "search": search,
            "orderByField": order_by_field,
            "orderByDirection": order_by_direction,
        }
        if keys:
            params["keys"] = keys
        if workflows:
            params["workflows"] = workflows
        if statuses:
            params["statuses"] = statuses
        if additional_metadata:
            params["additionalMetadata"] = additional_metadata

        return self._get(f"/api/v1/tenants/{tid}/events", params=params)

    def get_event(self, event_id: str) -> Dict[str, Any]:
        """
        Get event details.

        Args:
            event_id: The event ID

        Returns:
            Event information
        """
        return self._get(f"/api/v1/events/{event_id}")

    def get_event_data(self, event_id: str) -> Dict[str, Any]:
        """
        Get event payload data.

        Args:
            event_id: The event ID

        Returns:
            Event payload data
        """
        return self._get(f"/api/v1/events/{event_id}/data")

    def create_event(
        self,
        key: str,
        payload: Dict[str, Any],
        additional_metadata: Optional[Dict[str, str]] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a new event.

        Args:
            key: The event key/type
            payload: Event payload data
            additional_metadata: Additional metadata key-value pairs
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            The created event
        """
        tid = self._require_tenant(tenant_id)
        data = {"key": key, "payload": payload}
        if additional_metadata:
            data["additionalMetadata"] = additional_metadata
        return self._post(f"/api/v1/tenants/{tid}/events", json_data=data)

    def create_events_bulk(
        self,
        events: List[Dict[str, Any]],
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create multiple events in bulk.

        Args:
            events: List of events, each with 'key', 'payload', and optional 'additionalMetadata'
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            Created events
        """
        tid = self._require_tenant(tenant_id)
        return self._post(f"/api/v1/tenants/{tid}/events/bulk", json_data={"events": events})

    def replay_events(
        self,
        event_ids: List[str],
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Replay events.

        Args:
            event_ids: List of event IDs to replay
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            Replay result
        """
        tid = self._require_tenant(tenant_id)
        return self._post(f"/api/v1/tenants/{tid}/events/replay", json_data={"eventIds": event_ids})

    def list_event_keys(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        List all event keys used in the tenant.

        Args:
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            List of event keys
        """
        tid = self._require_tenant(tenant_id)
        return self._get(f"/api/v1/tenants/{tid}/events/keys")

    # =========================================================================
    # Workers
    # =========================================================================

    def list_workers(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        List all workers for the tenant.

        Args:
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            List of workers with their status and capabilities
        """
        tid = self._require_tenant(tenant_id)
        return self._get(f"/api/v1/tenants/{tid}/worker")

    def get_worker(self, worker_id: str) -> Dict[str, Any]:
        """
        Get worker details.

        Args:
            worker_id: The worker ID

        Returns:
            Detailed worker information
        """
        return self._get(f"/api/v1/workers/{worker_id}")

    # =========================================================================
    # Scheduled Runs
    # =========================================================================

    def list_scheduled_runs(
        self,
        tenant_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
        workflow_id: Optional[str] = None,
        order_by_field: Optional[str] = None,
        order_by_direction: Optional[str] = None,
        additional_metadata: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        List scheduled workflow runs.

        Args:
            tenant_id: The tenant ID. Uses default if not provided.
            offset: Pagination offset
            limit: Number of results to return
            workflow_id: Filter by workflow ID
            order_by_field: Field to order by
            order_by_direction: Order direction (ASC, DESC)
            additional_metadata: Filter by metadata

        Returns:
            List of scheduled runs
        """
        tid = self._require_tenant(tenant_id)
        params = {
            "offset": offset,
            "limit": min(limit, 50),
            "workflowId": workflow_id,
            "orderByField": order_by_field,
            "orderByDirection": order_by_direction,
        }
        if additional_metadata:
            params["additionalMetadata"] = additional_metadata
        return self._get(f"/api/v1/tenants/{tid}/workflows/scheduled", params=params)

    def get_scheduled_run(
        self, scheduled_run_id: str, tenant_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get scheduled run details.

        Args:
            scheduled_run_id: The scheduled run ID
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            Scheduled run details
        """
        tid = self._require_tenant(tenant_id)
        return self._get(f"/api/v1/tenants/{tid}/workflows/scheduled/{scheduled_run_id}")

    def schedule_workflow(
        self,
        workflow_id: str,
        trigger_at: str,
        input_data: Optional[Dict[str, Any]] = None,
        additional_metadata: Optional[Dict[str, str]] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Schedule a workflow to run at a specific time.

        Args:
            workflow_id: The workflow ID
            trigger_at: When to trigger (ISO 8601 timestamp)
            input_data: Input data for the workflow
            additional_metadata: Additional metadata
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            The scheduled run
        """
        tid = self._require_tenant(tenant_id)
        data = {"triggerAt": trigger_at}
        if input_data:
            data["input"] = input_data
        if additional_metadata:
            data["additionalMetadata"] = additional_metadata
        return self._post(f"/api/v1/tenants/{tid}/workflows/{workflow_id}/scheduled", json_data=data)

    def delete_scheduled_run(
        self, scheduled_run_id: str, tenant_id: Optional[str] = None
    ) -> None:
        """
        Delete a scheduled run.

        Args:
            scheduled_run_id: The scheduled run ID
            tenant_id: The tenant ID. Uses default if not provided.
        """
        tid = self._require_tenant(tenant_id)
        self._delete(f"/api/v1/tenants/{tid}/workflows/scheduled/{scheduled_run_id}")

    # =========================================================================
    # Cron Workflows
    # =========================================================================

    def list_crons(
        self,
        tenant_id: Optional[str] = None,
        offset: int = 0,
        limit: int = 50,
        workflow_id: Optional[str] = None,
        additional_metadata: Optional[List[str]] = None,
        order_by_field: Optional[str] = None,
        order_by_direction: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        List cron-triggered workflows.

        Args:
            tenant_id: The tenant ID. Uses default if not provided.
            offset: Pagination offset
            limit: Number of results to return
            workflow_id: Filter by workflow ID
            additional_metadata: Filter by metadata
            order_by_field: Field to order by
            order_by_direction: Order direction (ASC, DESC)

        Returns:
            List of cron workflows
        """
        tid = self._require_tenant(tenant_id)
        params = {
            "offset": offset,
            "limit": min(limit, 50),
            "workflowId": workflow_id,
            "orderByField": order_by_field,
            "orderByDirection": order_by_direction,
        }
        if additional_metadata:
            params["additionalMetadata"] = additional_metadata
        return self._get(f"/api/v1/tenants/{tid}/workflows/crons", params=params)

    def get_cron(self, cron_id: str, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get cron workflow details.

        Args:
            cron_id: The cron workflow ID
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            Cron workflow details including schedule and next run
        """
        tid = self._require_tenant(tenant_id)
        return self._get(f"/api/v1/tenants/{tid}/workflows/crons/{cron_id}")

    def create_cron(
        self,
        workflow_id: str,
        cron_expression: str,
        cron_name: Optional[str] = None,
        input_data: Optional[Dict[str, Any]] = None,
        additional_metadata: Optional[Dict[str, str]] = None,
        tenant_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a cron trigger for a workflow.

        Args:
            workflow_id: The workflow ID
            cron_expression: Cron schedule expression (e.g., "0 9 * * *")
            cron_name: Name for the cron job
            input_data: Input data for workflow runs
            additional_metadata: Additional metadata
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            The created cron workflow
        """
        tid = self._require_tenant(tenant_id)
        data = {"cronExpression": cron_expression}
        if cron_name:
            data["cronName"] = cron_name
        if input_data:
            data["input"] = input_data
        if additional_metadata:
            data["additionalMetadata"] = additional_metadata
        return self._post(f"/api/v1/tenants/{tid}/workflows/{workflow_id}/crons", json_data=data)

    def delete_cron(self, cron_id: str, tenant_id: Optional[str] = None) -> None:
        """
        Delete a cron workflow.

        Args:
            cron_id: The cron workflow ID
            tenant_id: The tenant ID. Uses default if not provided.
        """
        tid = self._require_tenant(tenant_id)
        self._delete(f"/api/v1/tenants/{tid}/workflows/crons/{cron_id}")

    # =========================================================================
    # Rate Limits
    # =========================================================================

    def list_rate_limits(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        """
        List rate limits for the tenant.

        Args:
            tenant_id: The tenant ID. Uses default if not provided.

        Returns:
            List of rate limit configurations
        """
        tid = self._require_tenant(tenant_id)
        return self._get(f"/api/v1/tenants/{tid}/rate-limits")

    # =========================================================================
    # Metadata
    # =========================================================================

    def get_api_metadata(self) -> Dict[str, Any]:
        """
        Get API metadata and server information.

        Returns:
            API metadata including version and capabilities
        """
        return self._get("/api/v1/meta")

    def get_api_version(self) -> Dict[str, Any]:
        """
        Get API version.

        Returns:
            API version information
        """
        return self._get("/api/v1/version")

    def check_health(self) -> bool:
        """
        Check if the API is healthy.

        Returns:
            True if healthy, raises exception otherwise
        """
        self._get("/api/ready")
        return True

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self) -> "HatchetClient":
        return self

    def __exit__(self, *args) -> None:
        self.close()
