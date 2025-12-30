"""
Fixed Django Ninja API demonstrating clean type generation.
"""
from ninja import NinjaAPI, Router
from .schemas_fixed import (
    CreateItemRequest,
    ItemResponse,
    AllRequiredResponse,
    CleanNullableSchema,
    UserProfileResponse,
)

api_fixed = NinjaAPI(
    title="Fixed Types Demo API",
    version="2.0.0",
    urls_namespace="api_fixed",
    description="Demonstrating how to get clean TypeScript types from Django Ninja",
)

router = Router(tags=["fixed"])


@router.post("/items", response=ItemResponse)
def create_item(request, payload: CreateItemRequest) -> ItemResponse:
    """
    CORRECT pattern: Different schemas for request and response.
    - CreateItemRequest: fields with defaults are optional (can omit)
    - ItemResponse: all fields are required (always present)
    """
    return ItemResponse(
        id=1,
        name=payload.name,
        count=payload.count,
        is_active=payload.is_active,
        priority=payload.priority,
        metadata=payload.metadata,
    )


@router.get("/all-required", response=AllRequiredResponse)
def get_all_required(request) -> AllRequiredResponse:
    """Response with all fields forced to required."""
    return AllRequiredResponse(name="test", count=5, is_active=True)


@router.post("/clean-nullable", response=CleanNullableSchema)
def create_clean_nullable(request, payload: CleanNullableSchema) -> CleanNullableSchema:
    """Clean nullable field handling."""
    return payload


@router.get("/profile/{user_id}", response=UserProfileResponse)
def get_profile(request, user_id: int) -> UserProfileResponse:
    """Using ResponseBase for automatic required fields."""
    return UserProfileResponse(
        id=user_id,
        username="johndoe",
        email="john@example.com",
        avatar_url=None,  # Nullable but always present
        created_at="2024-01-15T10:30:00Z",
    )


api_fixed.add_router("/", router)
