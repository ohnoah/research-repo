"""
Hatchet Sentry Integration

Works alongside Hatchet's OTel instrumentor. Adds Sentry isolation scopes,
user context, and tags to workflow tasks.

Setup:
    from hatchet_sentry import setup_hatchet_sentry

    setup_hatchet_sentry(
        sentry_dsn="https://...",
        # Optional: custom user extractor
        user_extractor=lambda action: action.additional_metadata.get("sentry_user"),
    )

Usage:
    # User workflows - pass sentry_user in metadata
    await hatchet.admin.aio_run_workflow(
        "OrderWorkflow",
        input={"order_id": "123"},
        options=TriggerWorkflowOptions(
            additional_metadata={"sentry_user": {"id": "u1", "email": "a@b.com"}}
        ),
    )

    # System workflows - no sentry_user, no problem
    await hatchet.admin.aio_run_workflow("CleanupWorkflow", input={})
"""

from __future__ import annotations

from collections.abc import Callable, Coroutine
from typing import TYPE_CHECKING, Any

import sentry_sdk

try:
    from wrapt import wrap_function_wrapper
except ImportError:
    raise ImportError("Install wrapt: pip install wrapt")

if TYPE_CHECKING:
    from hatchet_sdk.runnables.action import Action
    from hatchet_sdk.worker.runner.runner import Runner


UserExtractor = Callable[["Action"], dict[str, Any] | None]


def default_user_extractor(action: "Action") -> dict[str, Any] | None:
    """
    Extract user from (in order):
    1. additional_metadata.sentry_user
    2. action.action_payload.user_data (Hatchet's built-in field)
    """
    # Check metadata first (explicit opt-in)
    metadata = action.additional_metadata or {}
    if "sentry_user" in metadata:
        return metadata["sentry_user"]

    # Fall back to Hatchet's user_data field
    user_data = action.action_payload.user_data
    if user_data:
        return {
            "id": user_data.get("id") or user_data.get("user_id"),
            "email": user_data.get("email"),
            "username": user_data.get("username"),
        }

    return None


def setup_hatchet_sentry(
    sentry_dsn: str | None = None,
    user_extractor: UserExtractor | None = None,
    traces_sample_rate: float = 1.0,
    **sentry_kwargs: Any,
) -> None:
    """
    Set up Hatchet with Sentry and OTel integration.

    Args:
        sentry_dsn: Sentry DSN. If None, uses SENTRY_DSN env var.
        user_extractor: Function to extract user from Action. Default checks
                       additional_metadata.sentry_user and action.action_payload.user_data.
        traces_sample_rate: Sentry traces sample rate (default 1.0).
        **sentry_kwargs: Additional kwargs passed to sentry_sdk.init().

    Example:
        setup_hatchet_sentry(
            sentry_dsn="https://...",
            environment="production",
        )
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from sentry_sdk.integrations.opentelemetry import SentrySpanProcessor

    # 1. Set up OTel with Sentry
    provider = TracerProvider()
    provider.add_span_processor(SentrySpanProcessor())
    trace.set_tracer_provider(provider)

    # 2. Initialize Sentry
    sentry_sdk.init(
        dsn=sentry_dsn,
        traces_sample_rate=traces_sample_rate,
        **sentry_kwargs,
    )

    # 3. Initialize Hatchet OTel instrumentor
    from hatchet_sdk.opentelemetry import HatchetInstrumentor
    HatchetInstrumentor(tracer_provider=provider).instrument()

    # 4. Add our Sentry scope wrapper
    _user_extractor = user_extractor or default_user_extractor
    _instrument_sentry_scope(_user_extractor)


def _instrument_sentry_scope(user_extractor: UserExtractor) -> None:
    """Wrap Hatchet's task execution to add Sentry scopes."""
    import hatchet_sdk

    async def wrap_handle_start_step_run(
        wrapped: Callable[["Action"], Coroutine[None, None, Exception | None]],
        instance: "Runner",
        args: tuple["Action"],
        kwargs: Any,
    ) -> Exception | None:
        action = args[0]

        with sentry_sdk.isolation_scope() as scope:
            scope._name = "hatchet"
            scope.clear_breadcrumbs()

            # Set user if available
            user_data = user_extractor(action)
            if user_data:
                user_data = {k: v for k, v in user_data.items() if v is not None}
                if user_data:
                    scope.set_user(user_data)

            # Set tags
            task_name = action.action_id.split(":")[-1] if ":" in action.action_id else action.action_id
            scope.set_tag("hatchet.workflow", action.job_name)
            scope.set_tag("hatchet.task", task_name)
            scope.set_tag("hatchet.workflow_run_id", action.workflow_run_id)
            scope.set_tag("hatchet.retry_count", str(action.retry_count))

            if action.tenant_id:
                scope.set_tag("hatchet.tenant_id", action.tenant_id)

            # Set context
            scope.set_context("hatchet", {
                "workflow_name": action.job_name,
                "workflow_run_id": action.workflow_run_id,
                "workflow_id": action.workflow_id,
                "task_name": action.action_id,
                "step_run_id": action.step_run_id,
                "retry_count": action.retry_count,
                "worker_id": action.worker_id,
                "tenant_id": action.tenant_id,
                "parent_workflow_run_id": action.parent_workflow_run_id,
            })

            return await wrapped(*args, **kwargs)

    wrap_function_wrapper(
        hatchet_sdk,
        "worker.runner.runner.Runner.handle_start_step_run",
        wrap_handle_start_step_run,
    )


# =============================================================================
# Alternative: Manual instrumentation (if you need more control)
# =============================================================================

class HatchetSentryInstrumentor:
    """
    Manual instrumentor if you want to control setup yourself.

    Example:
        # Your own OTel/Sentry setup...

        instrumentor = HatchetSentryInstrumentor()
        instrumentor.instrument()
    """

    def __init__(self, user_extractor: UserExtractor | None = None):
        self.user_extractor = user_extractor or default_user_extractor
        self._instrumented = False

    def instrument(self) -> None:
        if self._instrumented:
            return
        _instrument_sentry_scope(self.user_extractor)
        self._instrumented = True
