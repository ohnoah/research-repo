"""
Utility for generating OpenAI-compatible JSON schema from Pydantic models.

This module provides functions to convert Pydantic models to JSON schemas
compatible with OpenAI's structured outputs / response_format for batch requests.
"""

import json
from typing import Type, TypeVar, Any

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def pydantic_to_openai_schema(model: Type[T]) -> dict[str, Any]:
    """
    Convert a Pydantic model to OpenAI-compatible JSON schema format.

    Uses OpenAI's internal helper which handles all the schema transformations
    needed for strict mode (additionalProperties: false, proper anyOf for Optional, etc.)

    Args:
        model: A Pydantic BaseModel class

    Returns:
        A dict with the structure:
        {
            "type": "json_schema",
            "json_schema": {
                "name": "<ModelName>",
                "strict": true,
                "schema": { ... }
            }
        }

    Example:
        >>> from pydantic import BaseModel
        >>> from typing import Optional
        >>>
        >>> class MyModel(BaseModel):
        ...     name: str
        ...     age: Optional[int]
        >>>
        >>> schema = pydantic_to_openai_schema(MyModel)
        >>> # Use in OpenAI batch request as response_format=schema
    """
    # Use OpenAI's internal helper - this is the cleanest approach
    # It handles all schema transformations including:
    # - Adding additionalProperties: false
    # - Converting Optional to anyOf with null
    # - Setting strict: true
    from openai.lib._parsing import type_to_response_format_param
    return type_to_response_format_param(model)


# Example usage and demonstration
if __name__ == "__main__":
    from typing import Literal, Optional

    NonInformationalSlideType = Literal[
        "table-of-contents", "cover-slide", "placeholder", "copyright", "terms-of-reference"
    ]

    class VisualDescription(BaseModel):
        visual_description: str
        non_informational_slide_type: Optional[NonInformationalSlideType]

    schema = pydantic_to_openai_schema(VisualDescription)
    print(json.dumps(schema, indent=2))
