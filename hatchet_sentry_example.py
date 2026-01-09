"""
Example: Using Hatchet with both OTel AND Sentry Integration

This shows how to set up both instrumentors to work together:
- Hatchet OTel Instrumentor: Creates spans for distributed tracing
- Hatchet Sentry Integration: Adds user context, tags, and scopes
"""

from pydantic import BaseModel
from hatchet_sdk import Hatchet, Context, TriggerWorkflowOptions
from hatchet_sdk.opentelemetry import HatchetInstrumentor

import sentry_sdk
from sentry_sdk.integrations.opentelemetry import SentrySpanProcessor
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider

from hatchet_sentry_integration import HatchetSentryIntegration


# =============================================================================
# Setup: Initialize both OTel and Sentry
# =============================================================================

# 1. Set up OpenTelemetry with Sentry span processor
provider = TracerProvider()
provider.add_span_processor(SentrySpanProcessor())
trace.set_tracer_provider(provider)

# 2. Initialize Sentry with the Hatchet integration
sentry_sdk.init(
    dsn="https://your-dsn@sentry.io/project",
    traces_sample_rate=1.0,
    integrations=[
        HatchetSentryIntegration(),  # Adds user context, tags, isolation scopes
    ],
)

# 3. Initialize Hatchet's OTel instrumentor (creates the actual spans)
HatchetInstrumentor(tracer_provider=provider).instrument()

# 4. Create Hatchet client
hatchet = Hatchet()


# =============================================================================
# Workflows - No special decorators needed!
# =============================================================================

class OrderInput(BaseModel):
    order_id: str
    items: list[dict]


@hatchet.workflow()
class OrderWorkflow:
    """User workflow - user context passed when triggering."""

    @hatchet.task()
    async def validate_order(self, input: OrderInput, ctx: Context) -> dict:
        # Sentry scope automatically has:
        # - User context (from additional_metadata.sentry_user)
        # - Tags: hatchet.workflow, hatchet.task, hatchet.workflow_run_id
        # - Full hatchet context in Sentry's context

        if not input.items:
            raise ValueError("Order must have items")  # Captured with full context

        return {"valid": True}

    @hatchet.task()
    async def process_order(self, input: OrderInput, ctx: Context) -> dict:
        return {"processed": True}


@hatchet.workflow()
class SystemCleanupWorkflow:
    """System workflow - no user, just runs."""

    @hatchet.task()
    async def cleanup_old_records(self, input: dict, ctx: Context) -> dict:
        # No user context here (none was passed), but still has:
        # - Tags: hatchet.workflow, hatchet.task, etc.
        # - Hatchet context for debugging
        return {"cleaned": 100}


# =============================================================================
# Triggering workflows
# =============================================================================

async def handle_user_request(user_id: str, user_email: str, order_data: dict):
    """When a user triggers a workflow, pass their info in metadata."""

    await hatchet.admin.aio_run_workflow(
        "OrderWorkflow",
        input=order_data,
        options=TriggerWorkflowOptions(
            additional_metadata={
                # This is picked up by HatchetSentryIntegration
                "sentry_user": {
                    "id": user_id,
                    "email": user_email,
                }
            }
        ),
    )


async def run_system_job():
    """System jobs don't need user context."""

    await hatchet.admin.aio_run_workflow(
        "SystemCleanupWorkflow",
        input={"max_age_days": 30},
        # No sentry_user - that's fine!
    )


# =============================================================================
# Helper for cleaner triggering
# =============================================================================

async def run_user_workflow(
    workflow_name: str,
    input: dict,
    user_id: str,
    user_email: str | None = None,
    **kwargs,
):
    """Helper to run workflows with user context."""
    return await hatchet.admin.aio_run_workflow(
        workflow_name,
        input=input,
        options=TriggerWorkflowOptions(
            additional_metadata={
                "sentry_user": {"id": user_id, "email": user_email},
                **kwargs.get("additional_metadata", {}),
            },
            **{k: v for k, v in kwargs.items() if k != "additional_metadata"},
        ),
    )


# Usage:
# await run_user_workflow("OrderWorkflow", {"order_id": "123"}, user_id="u1", user_email="a@b.com")


# =============================================================================
# Running the worker
# =============================================================================

if __name__ == "__main__":
    import asyncio

    async def main():
        worker = hatchet.worker("example-worker")
        worker.register_workflow(OrderWorkflow())
        worker.register_workflow(SystemCleanupWorkflow())

        print("Starting worker with OTel + Sentry integration...")
        print("- OTel creates spans for distributed tracing")
        print("- Sentry integration adds user context and tags")
        await worker.async_start()

    asyncio.run(main())
