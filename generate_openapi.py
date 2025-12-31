#!/usr/bin/env python
"""
Script to generate OpenAPI spec from Django Ninja API.
"""
import os
import sys
import json

# Set up Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "myproject.settings")

import django
django.setup()

from testapi.api import api

def main():
    # Get the OpenAPI schema
    schema = api.get_openapi_schema()

    # Write to file
    output_path = "openapi.json"
    with open(output_path, "w") as f:
        json.dump(schema, f, indent=2, default=str)

    print(f"OpenAPI spec written to {output_path}")
    print(f"Schema contains {len(schema.get('paths', {}))} endpoints")
    print(f"Schema contains {len(schema.get('components', {}).get('schemas', {}))} schemas")

if __name__ == "__main__":
    main()
