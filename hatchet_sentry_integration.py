"""
Sentry Integration for Hatchet.run Python SDK

Provides automatic Sentry scope wrapping for Hatchet workflow tasks.
Works alongside Hatchet's OTel instrumentor - use both together!

Usage:
    from hatchet_sdk import Hatchet
    from hatchet_sdk.opentelemetry import HatchetInstrumentor
    import sentry_sdk
    from sentry_sdk.integrations.opentelemetry import SentrySpanProcessor
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    from hatchet_sentry_integration import HatchetSentryIntegration

    # 1. Set up OTel with Sentry
    provider = TracerProvider()
    provider.add_span_processor(SentrySpanProcessor())
    trace.set_tracer_provider(provider)

    # 2. Initialize Sentry with both integrations
    sentry_sdk.init(
        dsn="your-dsn",
        integrations=[
            HatchetSentryIntegration(),  # Adds user context + tags
        ],
    )

    # 3. Initialize Hatchet OTel instrumentor (creates spans)
    HatchetInstrumentor(tracer_provider=provider).instrument()

    # 4. When running workflows WITH a user, pass user in metadata:
    await hatchet.admin.aio_run_workflow(
        "UserWorkflow",
        input={"order_id": "123"},
        options={"additional_metadata": {"sentry_user": {"id": "user-123", "email": "a@b.com"}}},
    )

    # System workflows just don't pass sentry_user - works fine, no user context
    await hatchet.admin.aio_run_workflow("SystemCleanupWorkflow", input={})
"""

from __future__ import annotations

import functools
from collections.abc import Callable, Coroutine
from contextlib import contextmanager
from typing import TYPE_CHECKING, Any, TypeVar

try:
    import sentry_sdk
    from sentry_sdk.integrations import DidNotEnable, Integration
except ImportError:
    raise ImportError(
        "sentry-sdk is required for HatchetSentryIntegration. "
        "Install it with: pip install sentry-sdk"
    )

try:
    from wrapt import wrap_function_wrapper  # type: ignore[import-untyped]
except ImportError:
    raise ImportError(
        "wrapt is required for HatchetSentryIntegration. "
        "Install it with: pip install wrapt"
    )

if TYPE_CHECKING:
    from hatchet_sdk.runnables.action import Action
    from hatchet_sdk.worker.runner.runner import Runner

R = TypeVar("R")

# Type for user extractor function
UserExtractor = Callable[["Action"], dict[str, Any] | None]
TagExtractor = Callable[["Action"], dict[str, str]]


def default_user_extractor(action: "Action") -> dict[str, Any] | None:
    """
    Default user extractor that looks for user data in multiple places:
    1. action.action_payload.user_data (Hatchet's built-in user_data field)
    2. action.additional_metadata.user or action.additional_metadata.sentry_user
    3. action.action_payload.input.user_id / user_email (common patterns)
    """
    # First, check Hatchet's built-in user_data field
    user_data = action.action_payload.user_data
    if user_data:
        return {
            "id": user_data.get("id") or user_data.get("user_id"),
            "email": user_data.get("email") or user_data.get("user_email"),
            "username": user_data.get("username") or user_data.get("name"),
            "ip_address": user_data.get("ip_address") or user_data.get("ip"),
            # Include any extra fields
            **{k: v for k, v in user_data.items() if k not in ("id", "user_id", "email", "user_email", "username", "name", "ip_address", "ip")},
        }

    # Check additional_metadata for user info
    metadata = action.additional_metadata or {}
    if "user" in metadata:
        return metadata["user"]
    if "sentry_user" in metadata:
        return metadata["sentry_user"]

    # Check workflow input for common user patterns
    input_data = action.action_payload.input or {}
    user_id = input_data.get("user_id") or input_data.get("userId")
    if user_id:
        return {
            "id": str(user_id),
            "email": input_data.get("user_email") or input_data.get("userEmail"),
        }

    return None


def default_tag_extractor(action: "Action") -> dict[str, str]:
    """
    Default tag extractor that adds useful Hatchet context as Sentry tags.
    """
    tags = {
        "hatchet.workflow": action.job_name,
        "hatchet.task": action.action_id.split(":")[-1] if ":" in action.action_id else action.action_id,
        "hatchet.workflow_run_id": action.workflow_run_id,
        "hatchet.step_run_id": action.step_run_id,
        "hatchet.retry_count": str(action.retry_count),
    }

    if action.tenant_id:
        tags["hatchet.tenant_id"] = action.tenant_id

    if action.parent_workflow_run_id:
        tags["hatchet.parent_workflow_run_id"] = action.parent_workflow_run_id

    if action.child_workflow_key:
        tags["hatchet.child_workflow_key"] = action.child_workflow_key

    return tags


class HatchetSentryIntegration(Integration):
    """
    Sentry integration for Hatchet.run that automatically wraps all workflow steps
    in Sentry isolation scopes with user context and tags.

    Example:
        sentry_sdk.init(
            dsn="...",
            integrations=[
                HatchetSentryIntegration(
                    user_extractor=lambda action: {
                        "id": action.action_payload.input.get("user_id"),
                    }
                )
            ],
        )
    """

    identifier = "hatchet"
    origin = "auto.queue.hatchet"

    def __init__(
        self,
        user_extractor: UserExtractor | None = None,
        tag_extractor: TagExtractor | None = None,
        set_transaction_name: bool = True,
        capture_task_errors: bool = True,
    ):
        """
        Initialize the Hatchet Sentry integration.

        Args:
            user_extractor: Function to extract user data from Action.
                           If None, uses default_user_extractor.
            tag_extractor: Function to extract tags from Action.
                          If None, uses default_tag_extractor.
            set_transaction_name: Whether to set the transaction name to the task name.
            capture_task_errors: Whether to capture task errors to Sentry.
        """
        self.user_extractor = user_extractor or default_user_extractor
        self.tag_extractor = tag_extractor or default_tag_extractor
        self.set_transaction_name = set_transaction_name
        self.capture_task_errors = capture_task_errors

    @staticmethod
    def setup_once() -> None:
        """Called once when the integration is set up."""
        try:
            import hatchet_sdk
        except ImportError:
            raise DidNotEnable("hatchet-sdk is not installed")

        # The actual wrapping happens in setup_once_with_options
        # because we need access to the integration instance

    def setup_once_with_options(self, options: dict[str, Any] | None = None) -> None:
        """Called after setup_once with the integration instance available."""
        import hatchet_sdk

        wrap_function_wrapper(
            hatchet_sdk,
            "worker.runner.runner.Runner.handle_start_step_run",
            self._wrap_handle_start_step_run,
        )

    async def _wrap_handle_start_step_run(
        self,
        wrapped: Callable[["Action"], Coroutine[None, None, Exception | None]],
        instance: "Runner",
        args: tuple["Action"],
        kwargs: Any,
    ) -> Exception | None:
        """Wrap handle_start_step_run to add Sentry scope."""
        action = args[0]

        # Create an isolation scope for this task execution
        with sentry_sdk.isolation_scope() as scope:
            scope._name = "hatchet"
            scope.clear_breadcrumbs()

            # Set user context
            user_data = self.user_extractor(action)
            if user_data:
                # Filter out None values
                user_data = {k: v for k, v in user_data.items() if v is not None}
                if user_data:
                    scope.set_user(user_data)

            # Set tags
            tags = self.tag_extractor(action)
            for key, value in tags.items():
                scope.set_tag(key, value)

            # Set context with full action details
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
                "child_workflow_index": action.child_workflow_index,
                "child_workflow_key": action.child_workflow_key,
                "priority": action.priority,
            })

            # Set transaction name if enabled and there's an active transaction
            if self.set_transaction_name:
                current_scope = sentry_sdk.get_current_scope()
                if current_scope and hasattr(current_scope, 'set_transaction_name'):
                    task_name = action.action_id.split(":")[-1] if ":" in action.action_id else action.action_id
                    current_scope.set_transaction_name(
                        f"{action.job_name}.{task_name}",
                        source="task",
                    )

            # Add breadcrumb for task start
            sentry_sdk.add_breadcrumb(
                category="hatchet",
                message=f"Starting task {action.action_id}",
                level="info",
                data={
                    "workflow": action.job_name,
                    "task": action.action_id,
                    "retry_count": action.retry_count,
                },
            )

            try:
                result = await wrapped(*args, **kwargs)

                # Add breadcrumb for task completion
                if result is None:
                    sentry_sdk.add_breadcrumb(
                        category="hatchet",
                        message=f"Completed task {action.action_id}",
                        level="info",
                    )
                else:
                    sentry_sdk.add_breadcrumb(
                        category="hatchet",
                        message=f"Task {action.action_id} failed",
                        level="error",
                        data={"error": str(result)},
                    )

                return result

            except Exception as e:
                if self.capture_task_errors:
                    sentry_sdk.capture_exception(e)
                raise


class HatchetSentryInstrumentor:
    """
    Standalone instrumentor for Hatchet Sentry integration.

    Use this if you prefer the instrumentor pattern over the Sentry integration pattern.
    This is useful if you want more control over when instrumentation is applied.

    Example:
        from hatchet_sentry_integration import HatchetSentryInstrumentor

        instrumentor = HatchetSentryInstrumentor(
            user_extractor=lambda action: {"id": action.action_payload.user_data.get("id")}
        )
        instrumentor.instrument()

        # Later, to remove instrumentation:
        instrumentor.uninstrument()
    """

    def __init__(
        self,
        user_extractor: UserExtractor | None = None,
        tag_extractor: TagExtractor | None = None,
        set_transaction_name: bool = True,
    ):
        self.user_extractor = user_extractor or default_user_extractor
        self.tag_extractor = tag_extractor or default_tag_extractor
        self.set_transaction_name = set_transaction_name
        self._instrumented = False

    def instrument(self) -> None:
        """Apply Sentry instrumentation to Hatchet."""
        if self._instrumented:
            return

        import hatchet_sdk

        wrap_function_wrapper(
            hatchet_sdk,
            "worker.runner.runner.Runner.handle_start_step_run",
            self._wrap_handle_start_step_run,
        )

        self._instrumented = True

    def uninstrument(self) -> None:
        """Remove Sentry instrumentation from Hatchet."""
        if not self._instrumented:
            return

        from opentelemetry.instrumentation.utils import unwrap
        import hatchet_sdk

        unwrap(hatchet_sdk.worker.runner.runner.Runner, "handle_start_step_run")
        self._instrumented = False

    async def _wrap_handle_start_step_run(
        self,
        wrapped: Callable[["Action"], Coroutine[None, None, Exception | None]],
        instance: "Runner",
        args: tuple["Action"],
        kwargs: Any,
    ) -> Exception | None:
        """Wrap handle_start_step_run to add Sentry scope."""
        action = args[0]

        with sentry_sdk.isolation_scope() as scope:
            scope._name = "hatchet"
            scope.clear_breadcrumbs()

            # Set user context
            user_data = self.user_extractor(action)
            if user_data:
                user_data = {k: v for k, v in user_data.items() if v is not None}
                if user_data:
                    scope.set_user(user_data)

            # Set tags
            tags = self.tag_extractor(action)
            for key, value in tags.items():
                scope.set_tag(key, value)

            # Set context
            scope.set_context("hatchet", {
                "workflow_name": action.job_name,
                "workflow_run_id": action.workflow_run_id,
                "task_name": action.action_id,
                "step_run_id": action.step_run_id,
                "retry_count": action.retry_count,
            })

            return await wrapped(*args, **kwargs)


# ============================================================================
# Decorator-based approach (alternative to global instrumentation)
# ============================================================================

def with_sentry_scope(
    user_extractor: UserExtractor | None = None,
    tag_extractor: TagExtractor | None = None,
    extra_tags: dict[str, str] | None = None,
):
    """
    Decorator to wrap a Hatchet task with Sentry scope.

    Use this if you want fine-grained control over which tasks get Sentry integration,
    or if you want different user extraction logic for different workflows.

    Example:
        @hatchet.workflow()
        class MyWorkflow:
            @with_sentry_scope(
                user_extractor=lambda action: {"id": action.action_payload.input.get("user_id")},
                extra_tags={"team": "backend"},
            )
            @hatchet.task()
            async def my_task(self, input: MyInput, ctx: Context) -> dict:
                # Sentry scope is automatically set up here
                return {"result": "success"}
    """
    _user_extractor = user_extractor or default_user_extractor
    _tag_extractor = tag_extractor or default_tag_extractor

    def decorator(func: Callable[..., R]) -> Callable[..., R]:
        @functools.wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> R:
            # Try to find the context argument which contains the action
            ctx = None
            for arg in args:
                if hasattr(arg, 'action'):
                    ctx = arg
                    break
            for v in kwargs.values():
                if hasattr(v, 'action'):
                    ctx = v
                    break

            if ctx is None:
                # No context found, just run the function
                return await func(*args, **kwargs)

            action = ctx.action

            with sentry_sdk.isolation_scope() as scope:
                scope._name = "hatchet"

                # Set user
                user_data = _user_extractor(action)
                if user_data:
                    user_data = {k: v for k, v in user_data.items() if v is not None}
                    if user_data:
                        scope.set_user(user_data)

                # Set tags
                tags = _tag_extractor(action)
                if extra_tags:
                    tags.update(extra_tags)
                for key, value in tags.items():
                    scope.set_tag(key, value)

                # Set context
                scope.set_context("hatchet", {
                    "workflow_name": action.job_name,
                    "task_name": action.action_id,
                    "workflow_run_id": action.workflow_run_id,
                })

                return await func(*args, **kwargs)

        @functools.wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> R:
            ctx = None
            for arg in args:
                if hasattr(arg, 'action'):
                    ctx = arg
                    break

            if ctx is None:
                return func(*args, **kwargs)

            action = ctx.action

            with sentry_sdk.isolation_scope() as scope:
                scope._name = "hatchet"

                user_data = _user_extractor(action)
                if user_data:
                    user_data = {k: v for k, v in user_data.items() if v is not None}
                    if user_data:
                        scope.set_user(user_data)

                tags = _tag_extractor(action)
                if extra_tags:
                    tags.update(extra_tags)
                for key, value in tags.items():
                    scope.set_tag(key, value)

                scope.set_context("hatchet", {
                    "workflow_name": action.job_name,
                    "task_name": action.action_id,
                    "workflow_run_id": action.workflow_run_id,
                })

                return func(*args, **kwargs)

        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper  # type: ignore
        return sync_wrapper  # type: ignore

    return decorator


# ============================================================================
# Workflow-level decorator that applies to all tasks
# ============================================================================

def sentry_workflow(
    user_extractor: UserExtractor | None = None,
    tag_extractor: TagExtractor | None = None,
    extra_tags: dict[str, str] | None = None,
):
    """
    Class decorator that automatically wraps all @task methods in a workflow with Sentry scope.

    This is the most ergonomic approach - just decorate your workflow class and all tasks
    automatically get Sentry integration.

    Example:
        @sentry_workflow(
            user_extractor=lambda action: {"id": action.action_payload.input.get("user_id")},
            extra_tags={"service": "payment-processor"},
        )
        @hatchet.workflow()
        class PaymentWorkflow:
            @hatchet.task()
            async def process_payment(self, input: PaymentInput, ctx: Context) -> dict:
                # Sentry scope is automatically set up!
                return {"status": "success"}

            @hatchet.task()
            async def send_receipt(self, input: PaymentInput, ctx: Context) -> dict:
                # This task also has Sentry scope!
                return {"sent": True}
    """
    _user_extractor = user_extractor or default_user_extractor
    _tag_extractor = tag_extractor or default_tag_extractor

    def class_decorator(cls: type) -> type:
        # Find and wrap all task methods
        for name in dir(cls):
            if name.startswith("_"):
                continue

            attr = getattr(cls, name)

            # Check if this is a Hatchet task (has _hatchet_task or similar marker)
            # The actual attribute name depends on Hatchet's implementation
            if callable(attr) and not isinstance(attr, type):
                # Wrap the method with Sentry scope
                wrapped = with_sentry_scope(
                    user_extractor=_user_extractor,
                    tag_extractor=_tag_extractor,
                    extra_tags=extra_tags,
                )(attr)
                setattr(cls, name, wrapped)

        return cls

    return class_decorator


# ============================================================================
# Context manager for manual scope management
# ============================================================================

@contextmanager
def hatchet_sentry_scope(
    action: "Action",
    user_extractor: UserExtractor | None = None,
    tag_extractor: TagExtractor | None = None,
    extra_tags: dict[str, str] | None = None,
):
    """
    Context manager for manually setting up Sentry scope with Hatchet context.

    Use this if you need maximum control over when the scope is active.

    Example:
        @hatchet.task()
        async def my_task(self, input: MyInput, ctx: Context) -> dict:
            # Do some work outside Sentry scope

            with hatchet_sentry_scope(ctx.action, extra_tags={"phase": "processing"}):
                # This code runs inside Sentry scope
                result = await process_data(input)

            # Back outside Sentry scope
            return result
    """
    _user_extractor = user_extractor or default_user_extractor
    _tag_extractor = tag_extractor or default_tag_extractor

    with sentry_sdk.isolation_scope() as scope:
        scope._name = "hatchet"
        scope.clear_breadcrumbs()

        # Set user
        user_data = _user_extractor(action)
        if user_data:
            user_data = {k: v for k, v in user_data.items() if v is not None}
            if user_data:
                scope.set_user(user_data)

        # Set tags
        tags = _tag_extractor(action)
        if extra_tags:
            tags.update(extra_tags)
        for key, value in tags.items():
            scope.set_tag(key, value)

        # Set context
        scope.set_context("hatchet", {
            "workflow_name": action.job_name,
            "workflow_run_id": action.workflow_run_id,
            "task_name": action.action_id,
            "step_run_id": action.step_run_id,
            "retry_count": action.retry_count,
            "worker_id": action.worker_id,
            "tenant_id": action.tenant_id,
        })

        yield scope
