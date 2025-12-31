"""
Comprehensive Pydantic schemas to test various field type patterns.
This file tests how Django Ninja + Hey API handles:
- Required vs optional fields
- Default values
- None/null handling
- Union types
- Various combinations
"""
from typing import Optional, Union, List, Literal
from datetime import datetime, date
from pydantic import BaseModel, Field
from enum import Enum


class Status(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    PENDING = "pending"


# =============================================================================
# PATTERN 1: Basic Required Fields (no defaults, no Optional)
# Expected: TypeScript should be required, not nullable
# =============================================================================
class RequiredFieldsSchema(BaseModel):
    """All fields are required with no defaults."""
    name: str
    age: int
    email: str
    is_active: bool


# =============================================================================
# PATTERN 2: Optional Fields (Optional[T] without defaults)
# Expected: TypeScript should be required but allow null
# =============================================================================
class OptionalFieldsSchema(BaseModel):
    """Fields that can be None but are still required in input."""
    name: str
    nickname: Optional[str]  # Can be None, but required to provide
    middle_name: str | None  # Same as above, Python 3.10+ syntax


# =============================================================================
# PATTERN 3: Fields with Default Values (not Optional)
# Expected: TypeScript should be optional (?) but not nullable
# =============================================================================
class DefaultValueFieldsSchema(BaseModel):
    """Fields with default values - should be optional in requests."""
    name: str
    count: int = 0
    is_enabled: bool = True
    description: str = "No description"


# =============================================================================
# PATTERN 4: Optional Fields with None Default
# Expected: TypeScript should be optional (?) AND nullable
# =============================================================================
class OptionalWithNoneDefaultSchema(BaseModel):
    """Optional fields with None as default - most permissive."""
    name: str
    nickname: Optional[str] = None
    bio: str | None = None
    avatar_url: Optional[str] = None


# =============================================================================
# PATTERN 5: Optional Fields with Non-None Default
# Expected: TypeScript should be optional (?) AND nullable
# =============================================================================
class OptionalWithValueDefaultSchema(BaseModel):
    """Optional fields but with non-None defaults."""
    name: str
    nickname: Optional[str] = "Anonymous"
    status: str | None = "pending"


# =============================================================================
# PATTERN 6: Mixed Patterns
# =============================================================================
class MixedPatternsSchema(BaseModel):
    """A realistic mix of patterns."""
    # Required, not nullable
    id: int
    name: str

    # Required, nullable
    parent_id: Optional[int]
    external_ref: int | None

    # Optional (has default), not nullable
    page: int = 1
    limit: int = 10
    sort_order: str = "asc"

    # Optional (has default), nullable
    filter_name: Optional[str] = None
    search_query: str | None = None

    # Optional with non-None default, nullable
    default_status: Optional[str] = "active"


# =============================================================================
# PATTERN 7: Using Field() with various configurations
# =============================================================================
class FieldDescriptorSchema(BaseModel):
    """Testing Field() descriptor patterns."""
    # Required field with Field()
    name: str = Field(..., min_length=1, max_length=100)

    # Required field with Field() and description
    email: str = Field(..., description="User's email address")

    # Optional with Field() default
    age: Optional[int] = Field(None, ge=0, le=150)

    # Default value via Field()
    country: str = Field("US", description="ISO country code")

    # Optional with non-None Field() default
    role: Optional[str] = Field("user", description="User role")


# =============================================================================
# PATTERN 8: Union Types
# =============================================================================
class UnionTypesSchema(BaseModel):
    """Testing Union type handling."""
    # Union of value types (not None)
    id: Union[int, str]

    # Union including None (equivalent to Optional)
    metadata: Union[dict, None]

    # Multiple type union
    value: Union[int, float, str]

    # Union with None and default
    tag: Union[str, None] = None


# =============================================================================
# PATTERN 9: Nested Schemas
# =============================================================================
class AddressSchema(BaseModel):
    street: str
    city: str
    country: str = "US"
    postal_code: Optional[str] = None


class NestedSchema(BaseModel):
    """Testing nested schema handling."""
    name: str

    # Required nested object
    primary_address: AddressSchema

    # Optional nested object
    billing_address: Optional[AddressSchema] = None

    # List of nested objects
    other_addresses: List[AddressSchema] = []


# =============================================================================
# PATTERN 10: Complex Realistic Example
# =============================================================================
class CreateUserRequest(BaseModel):
    """Realistic user creation request."""
    # Required fields
    username: str = Field(..., min_length=3, max_length=50)
    email: str = Field(..., description="Valid email address")
    password: str = Field(..., min_length=8)

    # Optional but not nullable
    age: int = Field(18, ge=0, le=150)

    # Optional and nullable
    display_name: Optional[str] = None
    bio: str | None = None
    website: Optional[str] = Field(None, description="Personal website URL")

    # Enum with default
    status: Status = Status.PENDING

    # Optional enum
    preferred_status: Optional[Status] = None

    # Nested
    address: Optional[AddressSchema] = None


class UserResponse(BaseModel):
    """User response with computed/readonly fields."""
    id: int
    username: str
    email: str
    display_name: Optional[str]
    bio: str | None
    status: Status
    created_at: datetime
    updated_at: Optional[datetime] = None


# =============================================================================
# PATTERN 11: Request vs Response Patterns
# =============================================================================
class ItemCreateRequest(BaseModel):
    """Create request - some fields optional with defaults."""
    name: str
    description: Optional[str] = None
    price: float
    quantity: int = 1
    is_available: bool = True
    category_id: Optional[int] = None


class ItemUpdateRequest(BaseModel):
    """Update request - all fields optional for partial updates."""
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[int] = None
    is_available: Optional[bool] = None
    category_id: Optional[int] = None


class ItemResponse(BaseModel):
    """Response - all fields populated."""
    id: int
    name: str
    description: Optional[str]
    price: float
    quantity: int
    is_available: bool
    category_id: Optional[int]
    created_at: datetime


# =============================================================================
# PATTERN 12: Literal Types
# =============================================================================
class LiteralTypesSchema(BaseModel):
    """Testing literal type handling."""
    sort_direction: Literal["asc", "desc"] = "asc"
    priority: Literal[1, 2, 3]
    optional_priority: Optional[Literal[1, 2, 3]] = None


# =============================================================================
# PATTERN 13: Default Factory (list, dict)
# =============================================================================
class DefaultFactorySchema(BaseModel):
    """Fields with default_factory equivalents."""
    name: str
    tags: List[str] = []
    metadata: dict = {}
    scores: List[int] = Field(default_factory=list)
    config: dict = Field(default_factory=dict)


# =============================================================================
# PATTERN 14: Query Parameter Patterns
# =============================================================================
class PaginationParams(BaseModel):
    """Typical pagination query params."""
    page: int = 1
    page_size: int = 20
    sort_by: Optional[str] = None
    sort_order: Literal["asc", "desc"] = "asc"


class FilterParams(BaseModel):
    """Filter parameters with various optional patterns."""
    search: Optional[str] = None
    status: Optional[Status] = None
    min_date: Optional[date] = None
    max_date: Optional[date] = None
    include_inactive: bool = False


# =============================================================================
# PATTERN 15: Strict vs Lenient Optionality
# =============================================================================
class StrictOptionalSchema(BaseModel):
    """
    Testing what should be 'required but can be null' vs 'optional and can be null'.

    In Pydantic:
    - Optional[T] without default = required in input, can be None
    - Optional[T] = None = not required, can be None
    """
    # Must provide this field, but value can be None
    nullable_required: Optional[str]

    # Don't need to provide this field, defaults to None
    nullable_optional: Optional[str] = None

    # Must provide this field, cannot be None
    required: str

    # Don't need to provide this field, has default, cannot be None
    optional_with_default: str = "default"
