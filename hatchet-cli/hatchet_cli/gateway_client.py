"""
Gateway client for Hatchet CLI.

Routes requests through the agent gateway instead of direct Hatchet API.
Only read-only operations are supported.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

import httpx

from .exceptions import HatchetAPIError, HatchetConfigurationError
from .config import get_config


class GatewayHatchetClient:
    """
    Client for the Hatchet gateway.

    Exposes a limited read-only surface via the gateway.
    """

    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        base_url: Optional[str] = None,
        gateway_token: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
        profile: Optional[str] = None,
    ) -> None:
        cfg = get_config()
        self.base_url = (
            base_url
            or os.getenv("GATEWAY_URL")
            or os.getenv("HATCHET_GATEWAY_URL")
            or cfg.get_gateway_url(profile)
        )
        self.gateway_token = (
            gateway_token
            or os.getenv("GATEWAY_TOKEN")
            or os.getenv("HATCHET_GATEWAY_TOKEN")
            or cfg.get_gateway_token(profile)
        )

        if not self.base_url:
            raise HatchetConfigurationError(
                "Gateway URL is required. Set via --gateway-url, GATEWAY_URL env var, or config."
            )
        if not self.gateway_token:
            raise HatchetConfigurationError(
                "Gateway token is required. Set via --gateway-token, GATEWAY_TOKEN env var, or config."
            )

        self.base_url = self.base_url.rstrip("/")
        self.timeout = timeout
        self._client = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self.gateway_token}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "hatchet-cli/1.0.0 (gateway)",
            },
        )

    def _handle_response(self, response: httpx.Response) -> Any:
        try:
            data = response.json() if response.content else {}
        except Exception:
            data = {"message": response.text}

        if response.status_code >= 400:
            message = data.get("error") if isinstance(data, dict) else None
            raise HatchetAPIError(message or response.text, status_code=response.status_code)

        return data

    def _request(self, method: str, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        if params:
            params = {k: v for k, v in params.items() if v is not None}
        response = self._client.request(method=method, url=path, params=params)
        return self._handle_response(response)

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        return self._request("GET", path, params=params)

    # =========================================================================
    # Supported read-only methods
    # =========================================================================

    def list_workflows(self, tenant_id: Optional[str] = None) -> Dict[str, Any]:
        return self._get("/v1/hatchet/workflows")

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
        params: Dict[str, Any] = {
            "workflow": workflow_id,
            "eventId": event_id,
            "parentRun": parent_workflow_run_id,
            "createdAfter": created_after,
            "createdBefore": created_before,
            "finishedAfter": finished_after,
            "finishedBefore": finished_before,
            "orderBy": order_by_field,
            "order": order_by_direction,
            "limit": min(limit, 50),
            "offset": offset,
        }
        if statuses:
            params["status"] = statuses
        if kinds:
            params["kind"] = kinds
        if additional_metadata:
            params["metadata"] = additional_metadata

        return self._get("/v1/hatchet/runs", params=params)

    def get_workflow_run(self, workflow_run_id: str) -> Dict[str, Any]:
        return self._get(f"/v1/hatchet/runs/{workflow_run_id}")

    def get_step_run_logs(self, step_run_id: str, offset: int = 0, limit: int = 100) -> Dict[str, Any]:
        return self._get(
            f"/v1/hatchet/steps/{step_run_id}/logs",
            params={"offset": offset, "limit": limit},
        )

    def __getattr__(self, name: str) -> Any:
        raise HatchetAPIError(f"Operation '{name}' is not supported in gateway mode.")
