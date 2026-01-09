"""
Example usage of Hatchet Sentry Integration

This file demonstrates all the different approaches to integrating Sentry with Hatchet.
Choose the approach that best fits your needs.
"""

import sentry_sdk
from pydantic import BaseModel
from hatchet_sdk import Context, Hatchet

# Import the integration
from hatchet_sentry_integration import (
    HatchetSentryIntegration,
    HatchetSentryInstrumentor,
    sentry_workflow,
    with_sentry_scope,
    hatchet_sentry_scope,
)

# ============================================================================
# APPROACH 1: Global Integration (Recommended - Most Ergonomic)
# ============================================================================
# This automatically wraps ALL Hatchet tasks with Sentry scope.
# Just add the integration to sentry_sdk.init() and you're done!

sentry_sdk.init(
    dsn="https://your-dsn@sentry.io/project",
    traces_sample_rate=1.0,
    integrations=[
        HatchetSentryIntegration(
            # Optional: customize user extraction
            user_extractor=lambda action: {
                "id": action.action_payload.input.get("user_id"),
                "email": action.action_payload.input.get("user_email"),
                # Or use Hatchet's built-in user_data field:
                # "id": action.action_payload.user_data.get("id"),
            },
            # Optional: add custom tags
            tag_extractor=lambda action: {
                "hatchet.workflow": action.job_name,
                "hatchet.task": action.action_id,
                "hatchet.workflow_run_id": action.workflow_run_id,
                "environment": action.additional_metadata.get("env", "production"),
            },
        )
    ],
)

hatchet = Hatchet()


# With APPROACH 1, these workflows automatically get Sentry integration!
class OrderInput(BaseModel):
    user_id: str
    user_email: str
    order_id: str
    items: list[dict]


@hatchet.workflow()
class OrderWorkflow:
    """All tasks in this workflow automatically have Sentry scope."""

    @hatchet.task()
    async def validate_order(self, input: OrderInput, ctx: Context) -> dict:
        # Sentry scope is automatically set with:
        # - User: {"id": input.user_id, "email": input.user_email}
        # - Tags: hatchet.workflow, hatchet.task, hatchet.workflow_run_id, etc.
        # - Context: full workflow/task details

        # Any error here will be captured with full context
        if not input.items:
            raise ValueError("Order must have at least one item")

        return {"valid": True, "item_count": len(input.items)}

    @hatchet.task()
    async def process_payment(self, input: OrderInput, ctx: Context) -> dict:
        # This task also has Sentry scope!
        sentry_sdk.add_breadcrumb(
            category="payment",
            message=f"Processing payment for order {input.order_id}",
            level="info",
        )
        return {"payment_status": "success"}


# ============================================================================
# APPROACH 2: Instrumentor Pattern (Alternative to Integration)
# ============================================================================
# Use this if you want to control when instrumentation is applied.

# instrumentor = HatchetSentryInstrumentor(
#     user_extractor=lambda action: {"id": action.action_payload.user_data.get("id")}
# )
# instrumentor.instrument()  # Apply instrumentation
# # ... later ...
# instrumentor.uninstrument()  # Remove instrumentation


# ============================================================================
# APPROACH 3: Workflow-Level Decorator (Per-Workflow Customization)
# ============================================================================
# Use this when you want different Sentry configuration for different workflows.


class PaymentInput(BaseModel):
    user_id: str
    amount: float
    currency: str


@sentry_workflow(
    user_extractor=lambda action: {
        "id": action.action_payload.input.get("user_id"),
    },
    extra_tags={
        "team": "payments",
        "pci_scope": "true",
    },
)
@hatchet.workflow()
class PaymentWorkflow:
    """This workflow has custom Sentry tags for the payments team."""

    @hatchet.task()
    async def process(self, input: PaymentInput, ctx: Context) -> dict:
        # Has Sentry scope with extra_tags: {"team": "payments", "pci_scope": "true"}
        return {"processed": True}


# ============================================================================
# APPROACH 4: Task-Level Decorator (Fine-Grained Control)
# ============================================================================
# Use this when only specific tasks need Sentry integration.


class AnalyticsInput(BaseModel):
    event_name: str
    user_id: str | None = None


@hatchet.workflow()
class AnalyticsWorkflow:
    @with_sentry_scope(
        user_extractor=lambda action: {"id": action.action_payload.input.get("user_id")},
        extra_tags={"analytics": "true"},
    )
    @hatchet.task()
    async def track_event(self, input: AnalyticsInput, ctx: Context) -> dict:
        # This specific task has Sentry scope
        return {"tracked": True}

    @hatchet.task()
    async def aggregate_metrics(self, input: AnalyticsInput, ctx: Context) -> dict:
        # This task does NOT have Sentry scope (no decorator)
        return {"aggregated": True}


# ============================================================================
# APPROACH 5: Context Manager (Maximum Control)
# ============================================================================
# Use this when you need to control exactly when the scope is active.


@hatchet.workflow()
class CustomScopeWorkflow:
    @hatchet.task()
    async def complex_task(self, input: OrderInput, ctx: Context) -> dict:
        # Phase 1: No Sentry scope
        preliminary_result = await self.preliminary_check(input)

        # Phase 2: With Sentry scope (only this section is wrapped)
        with hatchet_sentry_scope(
            ctx.action,
            extra_tags={"phase": "main_processing"},
        ) as scope:
            # Add dynamic user data
            scope.set_user({"id": input.user_id, "email": input.user_email})

            # Add breadcrumb
            sentry_sdk.add_breadcrumb(
                category="processing",
                message="Starting main processing",
                level="info",
            )

            result = await self.main_processing(input)

        # Phase 3: No Sentry scope again
        return {"result": result}

    async def preliminary_check(self, input: OrderInput) -> bool:
        return True

    async def main_processing(self, input: OrderInput) -> dict:
        return {"success": True}


# ============================================================================
# APPROACH 6: Using Hatchet's Built-in user_data (Cleanest)
# ============================================================================
# Hatchet has a built-in user_data field in ActionPayload.
# Pass user data when triggering workflows for automatic extraction.

# When triggering the workflow:
# await hatchet.workflows.trigger(
#     "OrderWorkflow",
#     input={"order_id": "123", "items": [...]},
#     options=TriggerWorkflowOptions(
#         additional_metadata={
#             "user": {  # Will be auto-extracted by default_user_extractor
#                 "id": "user-123",
#                 "email": "user@example.com",
#             }
#         }
#     ),
# )

# Or use Hatchet's user_data field directly in the action payload
# (requires Hatchet server configuration)


# ============================================================================
# Running the example
# ============================================================================

if __name__ == "__main__":
    import asyncio

    async def main():
        # Register workflows
        worker = hatchet.worker("sentry-example-worker")
        worker.register_workflow(OrderWorkflow())
        worker.register_workflow(PaymentWorkflow())
        worker.register_workflow(AnalyticsWorkflow())
        worker.register_workflow(CustomScopeWorkflow())

        print("Starting worker with Sentry integration...")
        await worker.async_start()

    asyncio.run(main())
