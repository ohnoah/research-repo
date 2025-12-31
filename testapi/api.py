"""
Django Ninja API endpoints to test various schema patterns.
"""
from typing import List
from ninja import NinjaAPI, Query
from datetime import datetime

from .schemas import (
    RequiredFieldsSchema,
    OptionalFieldsSchema,
    DefaultValueFieldsSchema,
    OptionalWithNoneDefaultSchema,
    OptionalWithValueDefaultSchema,
    MixedPatternsSchema,
    FieldDescriptorSchema,
    UnionTypesSchema,
    NestedSchema,
    CreateUserRequest,
    UserResponse,
    ItemCreateRequest,
    ItemUpdateRequest,
    ItemResponse,
    LiteralTypesSchema,
    DefaultFactorySchema,
    PaginationParams,
    FilterParams,
    StrictOptionalSchema,
    Status,
)

api = NinjaAPI(
    title="Type Testing API",
    description="API for testing OpenAPI -> TypeScript type generation",
    version="1.0.0",
)


# =============================================================================
# PATTERN 1: Required Fields
# =============================================================================
@api.post("/required-fields", response=RequiredFieldsSchema)
def create_required_fields(request, payload: RequiredFieldsSchema):
    """Test endpoint with all required fields."""
    return payload


# =============================================================================
# PATTERN 2: Optional Fields (no defaults)
# =============================================================================
@api.post("/optional-fields", response=OptionalFieldsSchema)
def create_optional_fields(request, payload: OptionalFieldsSchema):
    """Test endpoint with Optional[T] fields (no defaults)."""
    return payload


# =============================================================================
# PATTERN 3: Default Value Fields
# =============================================================================
@api.post("/default-value-fields", response=DefaultValueFieldsSchema)
def create_default_value_fields(request, payload: DefaultValueFieldsSchema):
    """Test endpoint with fields that have default values."""
    return payload


# =============================================================================
# PATTERN 4: Optional with None Default
# =============================================================================
@api.post("/optional-none-default", response=OptionalWithNoneDefaultSchema)
def create_optional_none_default(request, payload: OptionalWithNoneDefaultSchema):
    """Test endpoint with Optional[T] = None pattern."""
    return payload


# =============================================================================
# PATTERN 5: Optional with Value Default
# =============================================================================
@api.post("/optional-value-default", response=OptionalWithValueDefaultSchema)
def create_optional_value_default(request, payload: OptionalWithValueDefaultSchema):
    """Test endpoint with Optional[T] = 'value' pattern."""
    return payload


# =============================================================================
# PATTERN 6: Mixed Patterns
# =============================================================================
@api.post("/mixed-patterns", response=MixedPatternsSchema)
def create_mixed_patterns(request, payload: MixedPatternsSchema):
    """Test endpoint with mixed field patterns."""
    return payload


# =============================================================================
# PATTERN 7: Field Descriptors
# =============================================================================
@api.post("/field-descriptors", response=FieldDescriptorSchema)
def create_field_descriptors(request, payload: FieldDescriptorSchema):
    """Test endpoint with Field() descriptors."""
    return payload


# =============================================================================
# PATTERN 8: Union Types
# =============================================================================
@api.post("/union-types", response=UnionTypesSchema)
def create_union_types(request, payload: UnionTypesSchema):
    """Test endpoint with Union types."""
    return payload


# =============================================================================
# PATTERN 9: Nested Schemas
# =============================================================================
@api.post("/nested", response=NestedSchema)
def create_nested(request, payload: NestedSchema):
    """Test endpoint with nested schemas."""
    return payload


# =============================================================================
# PATTERN 10: User CRUD
# =============================================================================
@api.post("/users", response=UserResponse)
def create_user(request, payload: CreateUserRequest):
    """Create a new user."""
    return UserResponse(
        id=1,
        username=payload.username,
        email=payload.email,
        display_name=payload.display_name,
        bio=payload.bio,
        status=payload.status,
        created_at=datetime.now(),
    )


@api.get("/users/{user_id}", response=UserResponse)
def get_user(request, user_id: int):
    """Get a user by ID."""
    return UserResponse(
        id=user_id,
        username="testuser",
        email="test@example.com",
        display_name=None,
        bio=None,
        status=Status.ACTIVE,
        created_at=datetime.now(),
    )


# =============================================================================
# PATTERN 11: Item CRUD (Create vs Update)
# =============================================================================
@api.post("/items", response=ItemResponse)
def create_item(request, payload: ItemCreateRequest):
    """Create a new item."""
    return ItemResponse(
        id=1,
        name=payload.name,
        description=payload.description,
        price=payload.price,
        quantity=payload.quantity,
        is_available=payload.is_available,
        category_id=payload.category_id,
        created_at=datetime.now(),
    )


@api.patch("/items/{item_id}", response=ItemResponse)
def update_item(request, item_id: int, payload: ItemUpdateRequest):
    """Update an existing item (partial update)."""
    return ItemResponse(
        id=item_id,
        name=payload.name or "Existing Name",
        description=payload.description,
        price=payload.price or 9.99,
        quantity=payload.quantity or 1,
        is_available=payload.is_available if payload.is_available is not None else True,
        category_id=payload.category_id,
        created_at=datetime.now(),
    )


@api.get("/items", response=List[ItemResponse])
def list_items(request):
    """List all items."""
    return [
        ItemResponse(
            id=1,
            name="Item 1",
            description="Description 1",
            price=9.99,
            quantity=10,
            is_available=True,
            category_id=1,
            created_at=datetime.now(),
        )
    ]


# =============================================================================
# PATTERN 12: Literal Types
# =============================================================================
@api.post("/literal-types", response=LiteralTypesSchema)
def create_literal_types(request, payload: LiteralTypesSchema):
    """Test endpoint with Literal types."""
    return payload


# =============================================================================
# PATTERN 13: Default Factory
# =============================================================================
@api.post("/default-factory", response=DefaultFactorySchema)
def create_default_factory(request, payload: DefaultFactorySchema):
    """Test endpoint with default_factory patterns."""
    return payload


# =============================================================================
# PATTERN 14: Query Parameters
# =============================================================================
@api.get("/paginated-items", response=List[ItemResponse])
def list_paginated_items(
    request,
    pagination: PaginationParams = Query(...),
    filters: FilterParams = Query(...),
):
    """Test endpoint with query parameters using schemas."""
    return []


# =============================================================================
# PATTERN 15: Strict Optional
# =============================================================================
@api.post("/strict-optional", response=StrictOptionalSchema)
def create_strict_optional(request, payload: StrictOptionalSchema):
    """Test endpoint demonstrating strict optionality."""
    return payload


# =============================================================================
# Additional Tests: Path and Query Parameters
# =============================================================================
@api.get("/path-test/{required_id}")
def path_test(
    request,
    required_id: int,
    optional_param: str = None,
    default_param: int = 10,
):
    """Test path and query parameter handling."""
    return {
        "required_id": required_id,
        "optional_param": optional_param,
        "default_param": default_param,
    }


@api.get("/query-test")
def query_test(
    request,
    # Required query param
    required: str,
    # Optional query param (can be None)
    nullable: str = None,
    # Has default but not nullable
    with_default: int = 5,
    # Optional with explicit None default
    optional_nullable: str = None,
):
    """Test query parameter patterns."""
    return {
        "required": required,
        "nullable": nullable,
        "with_default": with_default,
        "optional_nullable": optional_nullable,
    }
