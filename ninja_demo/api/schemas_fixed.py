"""
FIXED schemas demonstrating how to get clean TypeScript types.

Key Problems Identified:
========================
1. Fields with defaults are NOT in OpenAPI `required` array
   - Pydantic: correct for requests (can omit field)
   - But WRONG for responses (field always present)
   - TypeScript generator adds `?` to non-required fields

2. Optional[T] = None generates `anyOf: [{type: T}, {type: null}]`
   - Combined with not being in `required`, you get `field?: T | null`
   - This is "triple optional" (undefined OR value OR null)

Solutions:
==========
1. SEPARATE Request and Response schemas (most important!)
2. For Response schemas: put ALL fields in `required` via model_config
3. Use `| None` instead of `Optional[]` for cleaner semantics
4. Consider post-processing OpenAPI spec for edge cases
"""
from typing import Annotated
from pydantic import BaseModel, Field, ConfigDict
from enum import Enum


class Priority(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


# ============================================================================
# SOLUTION 1: Separate Request and Response Schemas
# ============================================================================

class CreateItemRequest(BaseModel):
    """
    REQUEST schema - defaults are appropriate here.
    Fields with defaults CAN be omitted by the client.
    TypeScript: `field?: type` is CORRECT here.
    """
    name: str                              # Required, no default
    count: int = 0                         # Can be omitted, server uses 0
    is_active: bool = True                 # Can be omitted, server uses True
    priority: Priority = Priority.MEDIUM   # Can be omitted
    metadata: str | None = None            # Optional AND nullable


class ItemResponse(BaseModel):
    """
    RESPONSE schema - NO defaults, all fields are always present.
    TypeScript: all fields should be required (no `?`).
    """
    model_config = ConfigDict(
        # This ensures all defined fields are in the `required` array
        # even if they have defaults (though they shouldn't for responses)
        json_schema_extra={"required": ["id", "name", "count", "is_active", "priority", "metadata"]}
    )

    id: int
    name: str
    count: int           # Always present in response (no default needed!)
    is_active: bool      # Always present
    priority: Priority   # Always present
    metadata: str | None # Nullable but REQUIRED (always in response, could be null)


# ============================================================================
# SOLUTION 2: Use json_schema_extra to force required fields
# ============================================================================

class AllRequiredResponse(BaseModel):
    """
    Force all fields to be required using model_config.
    This fixes the 'default makes it optional' problem.
    """
    model_config = ConfigDict(
        json_schema_extra=lambda schema: schema.update(
            required=list(schema.get("properties", {}).keys())
        )
    )

    name: str
    count: int = 0        # Has default but will be in `required`
    is_active: bool = True


# ============================================================================
# SOLUTION 3: Nullable vs Optional - Pick ONE semantic
# ============================================================================

class CleanNullableSchema(BaseModel):
    """
    Use ONLY `| None` for nullable fields, NOT Optional.
    And be explicit about whether the field is required.
    """
    model_config = ConfigDict(
        json_schema_extra={"required": ["required_nullable", "required_non_null", "optional_nullable"]}
    )

    # Required AND can be null (server always returns this field, but value might be null)
    # TypeScript should be: `field: string | null` (no `?`)
    required_nullable: str | None

    # Required AND cannot be null
    # TypeScript: `field: string`
    required_non_null: str

    # Optional in request (can omit), null in response means "not set"
    # For requests: `field?: string | null`
    optional_nullable: str | None = None


# ============================================================================
# SOLUTION 4: Custom schema generator for responses
# ============================================================================

class ResponseBase(BaseModel):
    """
    Base class for all response schemas.
    Automatically makes all fields required.
    """

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        schema = super().model_json_schema(*args, **kwargs)
        # Force all properties to be required
        if "properties" in schema:
            schema["required"] = list(schema["properties"].keys())
        return schema


class UserProfileResponse(ResponseBase):
    """All fields will be required in OpenAPI schema."""
    id: int
    username: str
    email: str
    avatar_url: str | None  # Nullable but required
    created_at: str


# ============================================================================
# SOLUTION 5: Using Annotated for more control
# ============================================================================

class AnnotatedSchema(BaseModel):
    """Using Annotated for explicit field configuration."""

    # Truly required
    name: Annotated[str, Field(description="User's name")]

    # Required with default (for requests - can be omitted)
    role: Annotated[str, Field(default="user", description="User's role")]

    # Nullable and required (will be present but might be null)
    bio: Annotated[str | None, Field(description="User biography")]
