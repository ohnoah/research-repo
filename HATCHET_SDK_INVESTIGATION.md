# Hatchet SDK V1 Investigation: Namespace Isolation and Client Configuration

## Executive Summary

This document investigates three key questions about Hatchet SDK V1:
1. How workflow runs are dispatched only to workers from a specific test host/namespace
2. Whether namespace alone isolates actions
3. What paths could redirect a worker/run to a different Hatchet instance when overriding ClientConfig

## Key Findings

### 1. Namespace is a Client-Side Naming Convention, NOT Server-Side Isolation

**Namespace is simply a prefix applied to resource names.** It does not provide server-side isolation.

#### How Namespace Works (Python SDK - `config.py:150-159`)

```python
@field_validator("namespace")
@classmethod
def validate_namespace(cls, namespace: str) -> str:
    if not namespace:
        return ""

    if not namespace.endswith("_"):
        namespace = f"{namespace}_"

    return namespace.lower()
```

#### What Gets Namespaced

When you set `namespace="test"`, these resources get the `test_` prefix:
- **Workflow names**: `my_workflow` → `test_my_workflow`
- **Event names**: `user:create` → `test_user:create`
- **Worker names**: `my-worker` → `test_my-worker`
- **Action IDs**: `workflow:step` → `test_workflow:step`

#### Key Code Evidence

From `workflow.py:250`:
```python
@property
def name(self) -> str:
    """The (namespaced) name of the workflow."""
    return self.client.config.namespace + self.config.name
```

From `worker.py:94`:
```python
self.name = self.config.apply_namespace(name)
```

### 2. Tenant ID (From JWT) is the TRUE Isolation Boundary

**Workers can ONLY consume tasks from their own tenant.** The tenant ID is extracted from the JWT token and enforced server-side.

#### Server-Side Authentication (`middleware/auth.go:27-55`)

```go
func (a *GRPCAuthN) Middleware(ctx context.Context) (context.Context, error) {
    forbidden := status.Errorf(codes.Unauthenticated, "invalid auth token")
    token, err := auth.AuthFromMD(ctx, "bearer")

    if err != nil {
        return nil, forbidden
    }

    tenantId, tokenUUID, err := a.config.Auth.JWTManager.ValidateTenantToken(ctx, token)

    if err != nil {
        return nil, forbidden
    }

    queriedTenant, err := a.config.V1.Tenant().GetTenantByID(ctx, tenantId)

    if err != nil {
        return nil, forbidden
    }

    return context.WithValue(ctx, "tenant", queriedTenant), nil
}
```

#### Tenant Scoping in Dispatch (`dispatcher_v1.go:51-52`)

```go
bulkDatas, err := d.repov1.Tasks().ListTasks(ctx, msg.TenantID, taskIds)
```

Every database query and message queue operation is scoped by `tenantId`.

### Can Workers Outside the Namespace Still Consume Tasks?

**Yes, if they share the same tenant AND register the same action names.**

Namespace provides **naming isolation within a tenant**, not security isolation. Here's what happens:

| Scenario | Can Worker A consume Worker B's tasks? |
|----------|----------------------------------------|
| Same tenant, same namespace | Yes (if registered for same actions) |
| Same tenant, different namespace | **No** - action names differ due to prefix |
| Different tenant, same namespace | **No** - tenant isolation enforced server-side |
| Different tenant, different namespace | **No** - tenant isolation enforced server-side |

**Example**: If you have two workers in the same tenant:
- Worker A: `namespace="prod"`, actions = `["prod_myworkflow:step1"]`
- Worker B: `namespace="test"`, actions = `["test_myworkflow:step1"]`

They register for different action IDs, so task dispatch is naturally isolated.

### 3. ClientConfig Override Paths and Potential Leaks to Different Instances

#### Configuration Resolution Order (Priority: Highest to Lowest)

| Priority | Source | Environment Variable | Config Key |
|----------|--------|---------------------|------------|
| 1 | Explicit Code Override | N/A | Direct assignment |
| 2 | YAML Config | N/A | `.hatchet.yaml` |
| 3 | Environment Variable | `HATCHET_CLIENT_*` | N/A |
| 4 | **JWT Token Claims** | N/A | Embedded in token |

#### JWT Token Structure (`token.py:6-9`)

```python
class Claims(BaseModel):
    sub: str                    # tenant_id
    server_url: str             # REST API URL
    grpc_broadcast_address: str # gRPC endpoint
```

#### Critical: JWT Defaults Are Used When Config Not Explicitly Set

From `config.py:117-129`:
```python
@model_validator(mode="after")
def validate_addresses(self) -> "ClientConfig":
    server_url_from_jwt, grpc_broadcast_address_from_jwt = get_addresses_from_jwt(
        self.token
    )

    # Only override if NOT explicitly set in config
    if "host_port" not in self.model_fields_set:
        self.host_port = grpc_broadcast_address_from_jwt

    if "server_url" not in self.model_fields_set:
        self.server_url = server_url_from_jwt
```

#### Potential Paths to Different Hatchet Instance

| Risk Path | Description | Mitigation |
|-----------|-------------|------------|
| **JWT Token Swap** | Using a token from a different environment | Validate token source; use environment-specific tokens |
| **Partial Config Override** | Setting only `host_port` but not `server_url` | Always set both or neither; don't mix |
| **Environment Variable Leakage** | `HATCHET_CLIENT_TOKEN` from wrong env | Clear env vars; use explicit config |
| **Cached/Stale Token** | Reusing token with old server URLs | Token rotation; validate URLs match expected |
| **YAML Config Residue** | `.hatchet.yaml` pointing to wrong server | Delete/update config files per environment |

### Guaranteeing Dispatch to Specific Host/Namespace

To ensure workflow runs are dispatched ONLY to workers in a specific namespace:

#### 1. Use Consistent Namespace Configuration
```python
# Production worker
hatchet = Hatchet(ClientConfig(
    token=PROD_TOKEN,
    namespace="prod",
    host_port="prod.hatchet.example.com:7070",
    server_url="https://prod.hatchet.example.com"
))

# Test worker
hatchet = Hatchet(ClientConfig(
    token=TEST_TOKEN,
    namespace="test",
    host_port="test.hatchet.example.com:7070",
    server_url="https://test.hatchet.example.com"
))
```

#### 2. Validate Configuration at Startup
```python
def validate_hatchet_config(config: ClientConfig, expected_namespace: str, expected_host: str):
    assert config.namespace == f"{expected_namespace}_", f"Wrong namespace: {config.namespace}"
    assert expected_host in config.host_port, f"Wrong host: {config.host_port}"

    # Validate JWT claims match explicit config
    from hatchet_sdk.token import get_addresses_from_jwt
    jwt_server, jwt_grpc = get_addresses_from_jwt(config.token)

    if config.host_port != jwt_grpc:
        logger.warning(f"Config host_port ({config.host_port}) differs from JWT ({jwt_grpc})")
```

#### 3. Use Separate Tenants for True Isolation

For production vs. test isolation, **use different tenants** (different tokens), not just different namespaces. This provides server-enforced isolation.

## Summary Table

| Question | Answer |
|----------|--------|
| Does namespace isolate actions? | **Partially** - name prefixing only, not server-enforced |
| Can workers outside namespace consume tasks? | **No** - if namespace differs, action names differ |
| True isolation boundary? | **Tenant ID** (from JWT token) |
| JWT defaults risk? | **Yes** - if not explicitly overriding `host_port`/`server_url` |
| Override paths that could leak? | Token, env vars, YAML config, partial config |

## Recommendations

1. **For test isolation**: Use separate tenants (separate tokens), not just namespaces
2. **For namespace usage**: Treat it as a naming convention, not a security boundary
3. **For ClientConfig**: Always explicitly set `host_port` and `server_url` in code; don't rely on JWT defaults
4. **For CI/CD**: Clear `HATCHET_CLIENT_*` environment variables between environments
5. **For validation**: Add startup checks to validate config matches expected environment

## Files Analyzed

- `sdks/python/hatchet_sdk/config.py` - ClientConfig and namespace handling
- `sdks/python/hatchet_sdk/token.py` - JWT token parsing
- `sdks/python/hatchet_sdk/worker/worker.py` - Worker registration
- `sdks/python/hatchet_sdk/runnables/workflow.py` - Workflow name prefixing
- `sdks/typescript/src/util/config-loader/config-loader.ts` - TypeScript config loading
- `internal/services/grpc/middleware/auth.go` - Server-side auth
- `internal/services/dispatcher/server.go` - Worker registration
- `internal/services/dispatcher/dispatcher_v1.go` - Task dispatch
