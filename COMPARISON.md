# Type Comparison: Default vs Strict Mode

This document shows the differences in generated TypeScript types between the default OpenAPI spec and the "strict" version (with null types removed).

## Key Differences

### OptionalFieldsSchema (Optional[T] without default)

**Pydantic:**
```python
class OptionalFieldsSchema(BaseModel):
    name: str
    nickname: Optional[str]  # Required but nullable
    middle_name: str | None  # Required but nullable
```

**Default Mode (CORRECT for API):**
```typescript
export type OptionalFieldsSchema = {
    name: string;
    nickname: (string | null);    // ✓ Must provide, can be null
    middle_name: (string | null); // ✓ Must provide, can be null
};
```

**Strict Mode (LOSES null semantics):**
```typescript
export type OptionalFieldsSchema = {
    name: string;
    nickname: string;    // ✗ Cannot handle null from API!
    middle_name: string; // ✗ Cannot handle null from API!
};
```

### ItemResponse (Response with nullable fields)

**Pydantic:**
```python
class ItemResponse(BaseModel):
    id: int
    name: str
    description: Optional[str]  # In response, this is always present but may be null
    category_id: Optional[int]
```

**Default Mode (CORRECT):**
```typescript
export type ItemResponse = {
    id: number;
    name: string;
    description: (string | null);   // ✓ Field is present, may be null
    category_id: (number | null);   // ✓ Field is present, may be null
};
```

**Strict Mode (INCORRECT for nullable responses):**
```typescript
export type ItemResponse = {
    id: number;
    name: string;
    description: string;   // ✗ Runtime error if API returns null!
    category_id: number;   // ✗ Runtime error if API returns null!
};
```

### StrictOptionalSchema (The key test)

**Pydantic:**
```python
class StrictOptionalSchema(BaseModel):
    nullable_required: Optional[str]      # Must provide, can be null
    nullable_optional: Optional[str] = None  # Can omit, can be null
    required: str                         # Must provide, not null
    optional_with_default: str = "default"  # Can omit, not null
```

**Default Mode:**
```typescript
export type StrictOptionalSchema = {
    nullable_required: (string | null);  // Required, nullable
    nullable_optional?: (string | null); // Optional, nullable
    required: string;                    // Required, not nullable
    optional_with_default?: string;      // Optional, not nullable
};
```

**Strict Mode:**
```typescript
export type StrictOptionalSchema = {
    nullable_required: string;           // Required, NOT nullable (✗ WRONG!)
    nullable_optional?: string;          // Optional, NOT nullable
    required: string;                    // Required, not nullable
    optional_with_default?: string;      // Optional, not nullable
};
```

## When to Use Each Mode

### Use Default Mode (Recommended)

- When your API can return `null` values
- When `Optional[T]` without default means "required but can be null"
- For any production API where data integrity matters

### Use Strict Mode (With Caution)

- When you're 100% certain fields never contain `null`
- For APIs where `Optional` only means "has a default value"
- When you prefer simpler TypeScript types over runtime safety

## The Verdict

**Default mode is correct.** The `field?: (T | null)` pattern accurately represents:

1. `?` → Field can be omitted in requests (has default on server)
2. `| null` → Field can contain null value

If you want stricter types, the proper solution is to **change your Pydantic schemas** rather than post-processing the OpenAPI spec:

```python
# Instead of:
class MySchema(BaseModel):
    field: Optional[str] = None  # Generates field?: (string | null)

# Use:
class MySchema(BaseModel):
    field: str = ""  # Generates field?: string (no null)
```

## Summary Table

| Pydantic Pattern | Default TypeScript | Strict TypeScript | Notes |
|------------------|-------------------|-------------------|-------|
| `field: T` | `field: T` | `field: T` | Same |
| `field: Optional[T]` | `field: (T \| null)` | `field: T` | Strict loses null |
| `field: T = val` | `field?: T` | `field?: T` | Same |
| `field: Optional[T] = None` | `field?: (T \| null)` | `field?: T` | Strict loses null |
| `field: Optional[T] = val` | `field?: (T \| null)` | `field?: T` | Strict loses null |
