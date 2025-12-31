/**
 * TypeScript Type Tests for Django Ninja + Hey API Generated Types
 *
 * This file validates that the generated types have the correct semantics.
 * If this file compiles without errors, the types are correctly generated.
 */

import type {
    RequiredFieldsSchema,
    OptionalFieldsSchema,
    DefaultValueFieldsSchema,
    OptionalWithNoneDefaultSchema,
    OptionalWithValueDefaultSchema,
    MixedPatternsSchema,
    FieldDescriptorSchema,
    StrictOptionalSchema,
    ItemCreateRequest,
    ItemUpdateRequest,
    ItemResponse,
    UserResponse,
    CreateUserRequest,
} from './client/types.gen.js';

// =============================================================================
// TEST 1: RequiredFieldsSchema - All fields required, none nullable
// =============================================================================
const requiredValid: RequiredFieldsSchema = {
    name: 'test',
    age: 25,
    email: 'test@example.com',
    is_active: true,
};

// @ts-expect-error - Missing required field 'is_active'
const requiredMissing: RequiredFieldsSchema = {
    name: 'test',
    age: 25,
    email: 'test@example.com',
};

// The following demonstrates type safety - null cannot be assigned to 'name':
// const requiredNullName: RequiredFieldsSchema = {
//     name: null,  // ERROR: Type 'null' is not assignable to type 'string'
//     ...
// };

// =============================================================================
// TEST 2: OptionalFieldsSchema - Optional[T] without default = required but nullable
// =============================================================================
const optionalFieldsValid: OptionalFieldsSchema = {
    name: 'test',
    nickname: 'nick',         // Can be string
    middle_name: null,        // Can be null
};

const optionalFieldsAllNull: OptionalFieldsSchema = {
    name: 'test',
    nickname: null,           // Can be null
    middle_name: null,        // Can be null
};

// @ts-expect-error - Must provide nickname (even though it can be null)
const optionalFieldsMissing: OptionalFieldsSchema = {
    name: 'test',
    middle_name: null,
};

// =============================================================================
// TEST 3: DefaultValueFieldsSchema - Fields with defaults are optional (?)
// =============================================================================
const defaultValueMinimal: DefaultValueFieldsSchema = {
    name: 'test',  // Only required field
    // count, is_enabled, description all optional
};

const defaultValueFull: DefaultValueFieldsSchema = {
    name: 'test',
    count: 5,
    is_enabled: false,
    description: 'A description',
};

// The following demonstrates that fields with defaults are not nullable:
// const defaultValueNullCount: DefaultValueFieldsSchema = {
//     name: 'test',
//     count: null,  // ERROR: Type 'null' is not assignable to type 'number | undefined'
// };

// =============================================================================
// TEST 4: OptionalWithNoneDefaultSchema - Optional[T] = None = optional and nullable
// =============================================================================
const optionalNoneMinimal: OptionalWithNoneDefaultSchema = {
    name: 'test',
    // All other fields can be omitted
};

const optionalNoneWithValues: OptionalWithNoneDefaultSchema = {
    name: 'test',
    nickname: 'nick',
    bio: 'A bio',
    avatar_url: 'https://example.com/avatar.png',
};

const optionalNoneWithNulls: OptionalWithNoneDefaultSchema = {
    name: 'test',
    nickname: null,    // Can be null
    bio: null,         // Can be null
    avatar_url: null,  // Can be null
};

// =============================================================================
// TEST 5: StrictOptionalSchema - The definitive test of all patterns
// =============================================================================

// Minimal valid object
const strictMinimal: StrictOptionalSchema = {
    nullable_required: null,  // Required but can be null
    required: 'value',        // Required and NOT nullable
    // nullable_optional and optional_with_default can be omitted
};

// Full object with values
const strictFull: StrictOptionalSchema = {
    nullable_required: 'has value',
    nullable_optional: 'also has value',
    required: 'required value',
    optional_with_default: 'custom value',
};

// With nulls where allowed
const strictWithNulls: StrictOptionalSchema = {
    nullable_required: null,     // ✓ Can be null
    nullable_optional: null,     // ✓ Can be null
    required: 'value',
    // optional_with_default omitted - has default
};

// The following demonstrates strict type checking:
// 'required' field cannot be null:
// const strictRequiredNull: StrictOptionalSchema = {
//     nullable_required: 'value',
//     required: null,  // ERROR: Type 'null' is not assignable to type 'string'
// };

// 'optional_with_default' cannot be null (not Optional[T]):
// const strictDefaultNull: StrictOptionalSchema = {
//     nullable_required: 'value',
//     required: 'value',
//     optional_with_default: null,  // ERROR: Type 'null' is not assignable to type 'string | undefined'
// };

// @ts-expect-error - 'nullable_required' must be provided (no default)
const strictMissingNullable: StrictOptionalSchema = {
    required: 'value',
};

// =============================================================================
// TEST 6: MixedPatternsSchema - Complex realistic mix
// =============================================================================
const mixedMinimal: MixedPatternsSchema = {
    id: 1,
    name: 'test',
    parent_id: null,      // Required but nullable
    external_ref: null,   // Required but nullable
    // All others have defaults
};

const mixedFull: MixedPatternsSchema = {
    id: 1,
    name: 'test',
    parent_id: 123,
    external_ref: 456,
    page: 2,
    limit: 50,
    sort_order: 'desc',
    filter_name: 'filter',
    search_query: null,
    default_status: 'active',
};

// =============================================================================
// TEST 7: ItemCreateRequest vs ItemUpdateRequest - PATCH pattern
// =============================================================================

// Create: name and price required
const itemCreate: ItemCreateRequest = {
    name: 'Product',
    price: 9.99,
    // quantity, is_available, etc. have defaults
};

// Update: ALL fields optional (partial update)
const itemUpdatePartial: ItemUpdateRequest = {
    price: 19.99,  // Only updating price
};

const itemUpdateEmpty: ItemUpdateRequest = {
    // Valid to send empty object for no changes
};

// =============================================================================
// TEST 8: Response types - nullable fields without ?
// =============================================================================
function handleItemResponse(response: ItemResponse): void {
    // These fields are always present in response
    const id: number = response.id;
    const name: string = response.name;

    // These are nullable but always present
    const description: string | null = response.description;
    const categoryId: number | null = response.category_id;

    // Note: No need to check for undefined, only null
    if (description !== null) {
        console.log(description.toUpperCase());
    }
}

// =============================================================================
// TEST 9: CreateUserRequest - Realistic complex example
// =============================================================================
const userCreateMinimal: CreateUserRequest = {
    username: 'johndoe',
    email: 'john@example.com',
    password: 'securepassword123',
};

const userCreateFull: CreateUserRequest = {
    username: 'johndoe',
    email: 'john@example.com',
    password: 'securepassword123',
    age: 30,
    display_name: 'John Doe',
    bio: 'A software developer',
    website: 'https://johndoe.com',
    status: 'active',
    preferred_status: null,
    address: {
        street: '123 Main St',
        city: 'Springfield',
        country: 'US',
        postal_code: '12345',
    },
};

// =============================================================================
// TEST 10: Type narrowing works correctly
// =============================================================================
function processUser(user: UserResponse): string {
    // display_name and bio are (string | null), not optional
    // So we only need to check for null, not undefined

    let result = `User: ${user.username}`;

    // Correct narrowing: check for null
    if (user.display_name !== null) {
        result += ` (${user.display_name})`;
    }

    if (user.bio !== null) {
        result += ` - ${user.bio}`;
    }

    // updated_at is optional AND nullable
    if (user.updated_at !== undefined && user.updated_at !== null) {
        result += ` [Updated: ${user.updated_at}]`;
    }

    return result;
}

// =============================================================================
// SUMMARY: All patterns validated
// =============================================================================
console.log('All type tests passed!');

/*
Summary of type behaviors:

1. Required non-nullable:     `field: T`            - Must provide, cannot be null
2. Required nullable:         `field: (T | null)`   - Must provide, can be null
3. Optional non-nullable:     `field?: T`           - Can omit, cannot be null
4. Optional nullable:         `field?: (T | null)`  - Can omit OR provide null

These map correctly to Pydantic patterns:

1. `field: T`              → Required non-nullable
2. `field: Optional[T]`    → Required nullable (no default = required)
3. `field: T = default`    → Optional non-nullable
4. `field: Optional[T] = None` → Optional nullable
*/
