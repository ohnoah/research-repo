# Django Ninja + Pydantic + hey-api TypeScript Generation

## The Problem

When using Django Ninja with Pydantic schemas and generating TypeScript clients with hey-api, you often get "messy" types:

```typescript
// BEFORE (problematic)
export type DefaultValuesSchema = {
    title: string;
    count?: number;           // <- Should not be optional in response!
    is_active?: boolean;      // <- Same issue
    metadata?: string | null; // <- Triple optional (?, null, undefined)
};
```

### Root Causes

1. **Pydantic's OpenAPI Generation**: Fields with defaults are NOT added to the `required` array
   - Correct for REQUEST schemas (client can omit the field)
   - WRONG for RESPONSE schemas (field is always present)

2. **OpenAPI 3.1 nullable representation**: `Optional[str]` becomes `anyOf: [{type: string}, {type: null}]`
   - Combined with not being in `required`, TypeScript generators produce `field?: string | null`

## The Solutions

### Solution 1: Separate Request and Response Schemas (Recommended)

```python
class CreateItemRequest(BaseModel):
    """Request - defaults ARE appropriate (can omit fields)"""
    name: str
    count: int = 0           # Optional in request, has default
    is_active: bool = True

class ItemResponse(BaseModel):
    """Response - all fields always present"""
    id: int
    name: str
    count: int               # No default - always required
    is_active: bool
```

**Generated TypeScript:**
```typescript
// Request - optional fields are correct
export type CreateItemRequest = {
    name: string;
    count?: number;
    is_active?: boolean;
};

// Response - all required, clean!
export type ItemResponse = {
    id: number;
    name: string;
    count: number;
    is_active: boolean;
};
```

### Solution 2: Force All Fields Required with `json_schema_extra`

```python
class ItemResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "required": ["id", "name", "count", "is_active", "priority", "metadata"]
        }
    )

    id: int
    name: str
    count: int
    is_active: bool
    priority: Priority
    metadata: str | None  # Nullable but REQUIRED
```

### Solution 3: Create a ResponseBase Class

```python
class ResponseBase(BaseModel):
    """Base class that makes all fields required."""

    @classmethod
    def model_json_schema(cls, *args, **kwargs):
        schema = super().model_json_schema(*args, **kwargs)
        if "properties" in schema:
            schema["required"] = list(schema["properties"].keys())
        return schema


class UserProfileResponse(ResponseBase):
    id: int
    username: str
    email: str
    avatar_url: str | None  # Nullable but always present
```

### Solution 4: Use Dynamic json_schema_extra

```python
class AllRequiredResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra=lambda schema: schema.update(
            required=list(schema.get("properties", {}).keys())
        )
    )

    name: str
    count: int = 0        # Has default but will be in `required`
    is_active: bool = True
```

## Nullable vs Optional: Pick ONE Semantic

| Python Type | OpenAPI Result | TypeScript Result | Meaning |
|-------------|---------------|-------------------|---------|
| `str` | required, string | `field: string` | Required, non-null |
| `str \| None` (in required) | required, anyOf[str,null] | `field: string \| null` | Required, nullable |
| `str \| None = None` (not required) | not required, anyOf[str,null] | `field?: string \| null` | Optional, nullable |
| `str = "default"` (not required) | not required, string, default | `field?: string` | Optional with default |

## Key Takeaways

1. **Always use separate schemas for requests vs responses**
2. **Response schemas should have NO defaults** - all fields are always present
3. **Use `str | None` for nullable fields**, not `Optional[str]` (same effect, clearer intent)
4. **Force fields into `required` array** for response schemas using `json_schema_extra`
5. **Consider hey-api configuration** for additional control over generated types

## Files in This Demo

- `api/schemas.py` - Problematic schemas demonstrating the issues
- `api/schemas_fixed.py` - Fixed schemas with solutions
- `api/api.py` - API using problematic schemas
- `api/api_fixed.py` - API using fixed schemas
- `openapi.json` - Generated OpenAPI spec (problematic)
- `openapi_fixed.json` - Generated OpenAPI spec (fixed)
- `generated/` - TypeScript types from problematic spec
- `generated_fixed/` - TypeScript types from fixed spec

## Comparison

### Before (Problematic)
```typescript
export type DefaultValuesSchema = {
    title: string;
    count?: number;
    is_active?: boolean;
    priority?: Priority;
    metadata?: string | null;
};
```

### After (Fixed)
```typescript
export type ItemResponse = {
    id: number;
    name: string;
    count: number;          // Required!
    is_active: boolean;     // Required!
    priority: Priority;     // Required!
    metadata: string | null; // Required but nullable
};
```
