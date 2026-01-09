"""
Example Hatchet worker with Sentry + OTel integration
"""

from pydantic import BaseModel
from hatchet_sdk import Hatchet, Context, TriggerWorkflowOptions

from hatchet_sentry import setup_hatchet_sentry


# =============================================================================
# Setup (do this once at startup)
# =============================================================================

setup_hatchet_sentry(
    sentry_dsn="https://your-dsn@sentry.io/project",
    environment="production",
    # Optional: custom user extraction
    # user_extractor=lambda action: action.additional_metadata.get("user"),
)

hatchet = Hatchet()


# =============================================================================
# Workflows - nothing special needed!
# =============================================================================

class OrderInput(BaseModel):
    order_id: str
    items: list[dict]


@hatchet.workflow()
class OrderWorkflow:
    """User workflow - expects sentry_user in metadata."""

    @hatchet.task()
    async def validate(self, input: OrderInput, ctx: Context) -> dict:
        # Sentry scope has user context + hatchet tags
        if not input.items:
            raise ValueError("No items")  # Captured with full user context
        return {"valid": True}

    @hatchet.task()
    async def process(self, input: OrderInput, ctx: Context) -> dict:
        return {"processed": True}

    @hatchet.durable_task()
    async def wait_for_payment(self, input: OrderInput, ctx: Context) -> dict:
        # Durable tasks work the same way
        result = await ctx.aio_wait_for("payment", ...)
        return {"paid": True}


@hatchet.workflow()
class SystemCleanupWorkflow:
    """System workflow - no user needed."""

    @hatchet.task()
    async def cleanup(self, input: dict, ctx: Context) -> dict:
        # Still has hatchet tags, just no user
        return {"cleaned": 100}


# =============================================================================
# Triggering workflows
# =============================================================================

async def place_order(user_id: str, user_email: str, order: dict):
    """User action - include sentry_user."""
    await hatchet.admin.aio_run_workflow(
        "OrderWorkflow",
        input=order,
        options=TriggerWorkflowOptions(
            additional_metadata={
                "sentry_user": {"id": user_id, "email": user_email}
            }
        ),
    )


async def scheduled_cleanup():
    """System job - no user needed."""
    await hatchet.admin.aio_run_workflow(
        "SystemCleanupWorkflow",
        input={"max_age_days": 30},
    )


# =============================================================================
# Helper (optional convenience)
# =============================================================================

async def run_as_user(
    workflow: str,
    input: dict,
    user_id: str,
    user_email: str | None = None,
    **options,
):
    """Helper to run workflow with user context."""
    return await hatchet.admin.aio_run_workflow(
        workflow,
        input=input,
        options=TriggerWorkflowOptions(
            additional_metadata={
                "sentry_user": {"id": user_id, "email": user_email},
                **options.pop("additional_metadata", {}),
            },
            **options,
        ),
    )


# =============================================================================
# Run worker
# =============================================================================

if __name__ == "__main__":
    import asyncio

    async def main():
        worker = hatchet.worker("my-worker")
        worker.register_workflow(OrderWorkflow())
        worker.register_workflow(SystemCleanupWorkflow())
        await worker.async_start()

    asyncio.run(main())
