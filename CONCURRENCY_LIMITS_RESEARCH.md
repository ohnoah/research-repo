# Hatchet Concurrency Limits Research

## Question
Are concurrency limits on workflows/tasks in Hatchet cross-workflow or within-workflow? If I have the same key for two different workflows, do they count towards the same concurrency limit, or are different tasks always separated?

## Answer

**Concurrency limits are WITHIN-WORKFLOW, not cross-workflow.**

If you use the same concurrency key in two different workflows, they will have **completely separate concurrency limits**. Each workflow maintains its own concurrency accounting.

## Technical Analysis

### 1. Database Schema - Strategy Isolation

**File:** `sql/schema/v1-core.sql` (lines 163-179)

```sql
CREATE TABLE v1_step_concurrency (
    id bigint GENERATED ALWAYS AS IDENTITY,
    parent_strategy_id BIGINT,
    workflow_id UUID NOT NULL,
    workflow_version_id UUID NOT NULL,
    step_id UUID NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    strategy v1_concurrency_strategy NOT NULL,
    expression TEXT NOT NULL,
    tenant_id UUID NOT NULL,
    max_concurrency INTEGER NOT NULL,
    CONSTRAINT v1_step_concurrency_pkey PRIMARY KEY (workflow_id, workflow_version_id, step_id, id)
);
```

**Key observation:** The primary key includes `workflow_id` and `workflow_version_id`. Each workflow has its own strategy IDs. Two different workflows will have different `strategy_id` values even if they define identical concurrency logic.

### 2. Concurrency Slot Table - Key Scoping

**File:** `sql/schema/v1-core.sql` (lines 685-706)

```sql
CREATE TABLE v1_concurrency_slot (
    sort_id BIGINT GENERATED ALWAYS AS IDENTITY,
    task_id BIGINT NOT NULL,
    tenant_id UUID NOT NULL,
    workflow_id UUID NOT NULL,
    workflow_version_id UUID NOT NULL,
    workflow_run_id UUID NOT NULL,
    strategy_id BIGINT NOT NULL,
    key TEXT NOT NULL,
    is_filled BOOLEAN NOT NULL DEFAULT FALSE,
    ...
);

CREATE INDEX v1_concurrency_slot_query_idx ON v1_concurrency_slot
  (tenant_id, strategy_id ASC, key ASC, sort_id ASC);
```

**Key observation:** The concurrency slot includes both `workflow_id` and `workflow_version_id`. The lookup index uses `strategy_id`, which is workflow-specific.

### 3. Concurrency Limit Enforcement - Strategy ID Filtering

**File:** `pkg/repository/v1/sqlcv1/concurrency.sql` (lines 174-193)

```sql
-- name: RunGroupRoundRobin :many
WITH eligible_slots_per_group AS (
    SELECT cs.*
    FROM (
        SELECT DISTINCT key
        FROM v1_concurrency_slot
        WHERE
            tenant_id = @tenantId::uuid
            AND strategy_id = @strategyId::bigint    -- <-- WORKFLOW-SPECIFIC!
    ) distinct_keys
    JOIN LATERAL (
        SELECT *
        FROM v1_concurrency_slot wcs_all
        WHERE
            wcs_all.key = distinct_keys.key
            AND wcs_all.tenant_id = @tenantId::uuid
            AND wcs_all.strategy_id = @strategyId::bigint    -- <-- FILTERS BY STRATEGY_ID
        ORDER BY wcs_all.sort_id ASC
        LIMIT @maxRuns::int    -- <-- MAX CONCURRENCY PER KEY
    ) cs ON true
```

**Key observation:** The query limits results by BOTH `strategy_id` AND `key`. Since each workflow has its own `strategy_id`, queries from different workflows don't interfere with each other.

### 4. Task Creation - Strategy Assignment

**File:** `pkg/repository/v1/task.go` (lines 1835-1849)

Strategies are looked up per step using workflow-version-specific data. Each workflow version has its own set of strategy IDs.

### 5. Workflow-Level Concurrency

**File:** `sql/schema/v1-core.sql` (lines 147-161)

```sql
CREATE TABLE v1_workflow_concurrency (
    id bigint GENERATED ALWAYS AS IDENTITY,
    workflow_id UUID NOT NULL,
    workflow_version_id UUID NOT NULL,
    ...
);
```

Even workflow-level concurrency is scoped to a specific `workflow_id` and `workflow_version_id`.

## Practical Example

If you have:
- **Workflow A** with `maxConcurrency: 5` and key expression `input.userId`
- **Workflow B** with `maxConcurrency: 5` and key expression `input.userId`

And user "123" triggers both workflows:
- Workflow A can run **5** concurrent tasks for user "123"
- Workflow B can **also** run **5** concurrent tasks for user "123" simultaneously
- **Total: 10 concurrent tasks** for user "123" across both workflows

## Conclusion

The architecture clearly shows that concurrency limits are isolated per workflow:

1. **Strategy IDs are workflow-specific** - Each workflow version gets its own strategy ID sequence
2. **Slots are queried by strategy_id** - Concurrency enforcement queries filter by both `strategy_id` (workflow-specific) and `key` (expression-evaluated)
3. **Different workflows have different strategy IDs** - Even with identical concurrency expressions, two workflows will have separate strategy IDs
4. **Cross-workflow sharing is not possible** - The database schema and query logic make it impossible for concurrency limits to span across different workflows

**Bottom line:** If you want to share concurrency limits across different "logical" workflows, you would need to combine them into a single Hatchet workflow (possibly with conditional branching).
