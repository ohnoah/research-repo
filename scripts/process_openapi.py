#!/usr/bin/env python
"""
OpenAPI Spec Post-Processor

This script demonstrates how to modify the OpenAPI spec to achieve
different type generation behaviors. This can be used as a workaround
if the default behavior doesn't match your needs.

Usage:
    python scripts/process_openapi.py

This will read openapi.json and write openapi-processed.json
"""
import json
from typing import Any
from copy import deepcopy


def remove_null_from_anyof(schema: dict) -> dict:
    """
    Remove 'null' type from anyOf arrays, making fields non-nullable.
    Use this if you want stricter types in TypeScript.
    """
    if 'anyOf' in schema:
        non_null_types = [t for t in schema['anyOf'] if t.get('type') != 'null']
        if len(non_null_types) == 1:
            # Replace anyOf with the single remaining type
            result = deepcopy(non_null_types[0])
            # Preserve other properties like 'title', 'description', 'default'
            for key in ['title', 'description', 'default']:
                if key in schema:
                    result[key] = schema[key]
            return result
        elif len(non_null_types) > 1:
            schema = deepcopy(schema)
            schema['anyOf'] = non_null_types
    return schema


def add_null_to_optional(schema: dict, required: list) -> dict:
    """
    For fields that are optional (not in required), ensure they have | null.
    This is the opposite transformation - ensuring nullable where optional.
    """
    if 'properties' in schema:
        schema = deepcopy(schema)
        for prop_name, prop_schema in schema['properties'].items():
            if prop_name not in required:
                # Field is optional, ensure it can be null
                if 'anyOf' not in prop_schema and 'type' in prop_schema:
                    if prop_schema.get('type') != 'null':
                        schema['properties'][prop_name] = {
                            'anyOf': [
                                prop_schema,
                                {'type': 'null'}
                            ]
                        }
    return schema


def process_schema(schema: dict, mode: str = 'strict') -> dict:
    """
    Process a schema recursively.

    Modes:
    - 'strict': Remove null from anyOf (TypeScript fields won't be nullable)
    - 'lenient': Add null to all optional fields
    - 'default': Keep as-is
    """
    if not isinstance(schema, dict):
        return schema

    schema = deepcopy(schema)

    if mode == 'strict':
        schema = remove_null_from_anyof(schema)

    # Recurse into nested structures
    if 'properties' in schema:
        required = schema.get('required', [])
        for prop_name, prop_schema in schema['properties'].items():
            schema['properties'][prop_name] = process_schema(prop_schema, mode)

    if 'items' in schema:
        schema['items'] = process_schema(schema['items'], mode)

    if 'anyOf' in schema:
        schema['anyOf'] = [process_schema(s, mode) for s in schema['anyOf']]

    if 'allOf' in schema:
        schema['allOf'] = [process_schema(s, mode) for s in schema['allOf']]

    if 'oneOf' in schema:
        schema['oneOf'] = [process_schema(s, mode) for s in schema['oneOf']]

    return schema


def process_openapi_spec(spec: dict, mode: str = 'default') -> dict:
    """Process the entire OpenAPI specification."""
    spec = deepcopy(spec)

    # Process component schemas
    if 'components' in spec and 'schemas' in spec['components']:
        for schema_name, schema in spec['components']['schemas'].items():
            spec['components']['schemas'][schema_name] = process_schema(schema, mode)

    return spec


def main():
    # Read the original spec
    with open('openapi.json', 'r') as f:
        spec = json.load(f)

    print("Processing OpenAPI spec...")
    print(f"Original spec has {len(spec.get('components', {}).get('schemas', {}))} schemas")

    # Create different versions for comparison
    modes = ['default', 'strict']

    for mode in modes:
        processed = process_openapi_spec(spec, mode)
        output_file = f'openapi-{mode}.json' if mode != 'default' else 'openapi.json'

        with open(output_file, 'w') as f:
            json.dump(processed, f, indent=2)

        print(f"  Written: {output_file} (mode: {mode})")

    # Also create a summary of the differences
    print("\n" + "=" * 60)
    print("SUMMARY: How each mode affects type generation")
    print("=" * 60)

    print("""
DEFAULT MODE (current behavior):
  - Optional[T] without default → Required, nullable: field: (T | null)
  - Optional[T] = None → Optional, nullable: field?: (T | null)
  - T = default → Optional, not nullable: field?: T

STRICT MODE (removes null from anyOf):
  - Optional[T] without default → Required, NOT nullable: field: T
  - Optional[T] = None → Optional, NOT nullable: field?: T
  - T = default → Optional, not nullable: field?: T

NOTE: Strict mode may cause runtime issues if your API actually returns null!
Only use if you're sure the API never returns null for these fields.
""")


if __name__ == '__main__':
    main()
