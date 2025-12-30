"""
Demonstration of different Pydantic field configurations and how they
appear in OpenAPI spec (and subsequently in generated TypeScript clients).
"""
from typing import Optional
from pydantic import BaseModel, Field
from enum import Enum


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ============================================================================
# SCENARIO 1: Basic Required vs Optional
# ============================================================================

class BasicSchema(BaseModel):
    """Basic required and optional fields."""

    # Required - no default, no Optional
    name: str

    # Optional with None default - can be null
    nickname: Optional[str] = None

    # Optional without default - still required but can be null
    description: Optional[str]


# ============================================================================
# SCENARIO 2: Default Values (The Problematic Case)
# ============================================================================

class DefaultValuesSchema(BaseModel):
    """Fields with default values - often incorrectly marked as optional in OpenAPI."""

    # Required - no default
    title: str

    # Has default but is NOT optional - you can omit it, but it's always present in response
    count: int = 0
    is_active: bool = True
    priority: Priority = Priority.MEDIUM

    # Optional with default None
    metadata: Optional[str] = None


# ============================================================================
# SCENARIO 3: Field() with various configurations
# ============================================================================

class FieldConfigSchema(BaseModel):
    """Using Field() for more control."""

    # Required with validation
    email: str = Field(..., description="User's email address")

    # Default value via Field
    max_retries: int = Field(default=3, ge=0, le=10)

    # Optional via Field
    notes: Optional[str] = Field(default=None, max_length=500)

    # Default factory (for mutable defaults)
    tags: list[str] = Field(default_factory=list)


# ============================================================================
# SCENARIO 4: Request vs Response schemas (important distinction!)
# ============================================================================

class CreateUserRequest(BaseModel):
    """Request schema - fields user must/can provide."""

    username: str
    email: str

    # Optional in request - server will use default if not provided
    role: str = "user"
    is_verified: bool = False


class UserResponse(BaseModel):
    """Response schema - fields always present in response."""

    id: int
    username: str
    email: str
    role: str  # Always present in response (no default needed)
    is_verified: bool  # Always present in response
    created_at: str


# ============================================================================
# SCENARIO 5: Nested schemas
# ============================================================================

class Address(BaseModel):
    street: str
    city: str
    country: str = "USA"


class PersonWithAddress(BaseModel):
    name: str

    # Required nested object
    primary_address: Address

    # Optional nested object
    secondary_address: Optional[Address] = None


# ============================================================================
# SCENARIO 6: The problematic union types
# ============================================================================

class ProblematicSchema(BaseModel):
    """This often generates messy TypeScript types."""

    # These all might generate `field?: type | null | undefined`
    optional_with_default: Optional[str] = None
    optional_without_default: Optional[str] = Field(default=None)

    # Non-optional with default - might incorrectly get `?` in TS
    has_default: str = "default_value"
