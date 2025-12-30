#!/usr/bin/env python
"""Export fixed OpenAPI spec from Django Ninja API."""
import os
import sys
import json

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from api.api_fixed import api_fixed

# Get OpenAPI schema
schema = api_fixed.get_openapi_schema()

# Save to file
with open("openapi_fixed.json", "w") as f:
    json.dump(schema, f, indent=2)

print("Fixed OpenAPI spec exported to openapi_fixed.json")
print("\n" + "=" * 70)
print("FIXED SCHEMA ANALYSIS:")
print("=" * 70)

# Analyze the schemas
components = schema.get("components", {}).get("schemas", {})

for name, schema_def in components.items():
    print(f"\n### {name} ###")
    props = schema_def.get("properties", {})
    required = schema_def.get("required", [])

    print(f"  Required fields: {required}")

    for prop_name, prop_def in props.items():
        is_required = prop_name in required
        has_default = "default" in prop_def
        is_nullable = prop_def.get("anyOf") or prop_def.get("oneOf")

        status = []
        if is_required:
            status.append("REQUIRED")
        else:
            status.append("optional")
        if has_default:
            status.append(f"default={prop_def.get('default')}")
        if is_nullable:
            status.append("NULLABLE")

        print(f"  - {prop_name}: {', '.join(status)}")
