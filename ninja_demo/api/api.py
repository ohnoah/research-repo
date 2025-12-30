"""
Django Ninja API with various endpoint configurations.
"""
from ninja import NinjaAPI, Router
from .schemas import (
    BasicSchema,
    DefaultValuesSchema,
    FieldConfigSchema,
    CreateUserRequest,
    UserResponse,
    PersonWithAddress,
    ProblematicSchema,
)

api = NinjaAPI(
    title="Field Types Demo API",
    version="1.0.0",
    description="Demonstrating how different Pydantic field configs appear in OpenAPI",
)

router = Router(tags=["demo"])


# ============================================================================
# Endpoints demonstrating each schema type
# ============================================================================

@router.post("/basic", response=BasicSchema)
def create_basic(request, payload: BasicSchema) -> BasicSchema:
    """Endpoint using BasicSchema for both request and response."""
    return payload


@router.post("/default-values", response=DefaultValuesSchema)
def create_with_defaults(request, payload: DefaultValuesSchema) -> DefaultValuesSchema:
    """Endpoint with default values - watch how these appear in OpenAPI."""
    return payload


@router.post("/field-config", response=FieldConfigSchema)
def create_field_config(request, payload: FieldConfigSchema) -> FieldConfigSchema:
    """Endpoint using Field() configurations."""
    return payload


@router.post("/users", response=UserResponse)
def create_user(request, payload: CreateUserRequest) -> UserResponse:
    """Create user - different schemas for request vs response."""
    return UserResponse(
        id=1,
        username=payload.username,
        email=payload.email,
        role=payload.role,
        is_verified=payload.is_verified,
        created_at="2024-01-15T10:30:00Z",
    )


@router.post("/person-address", response=PersonWithAddress)
def create_person(request, payload: PersonWithAddress) -> PersonWithAddress:
    """Nested schema example."""
    return payload


@router.post("/problematic", response=ProblematicSchema)
def create_problematic(request, payload: ProblematicSchema) -> ProblematicSchema:
    """The problematic schema that generates messy types."""
    return payload


api.add_router("/", router)
