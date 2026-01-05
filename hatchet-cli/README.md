# Hatchet CLI

A comprehensive command-line interface for [Hatchet](https://hatchet.run) - the modern orchestration platform for background tasks and workflow automation.

## Features

- **Workflow Management**: List, view, trigger, and delete workflows
- **Run Operations**: List, filter, inspect, cancel, and replay workflow runs
- **Step Run Inspection**: View step details, logs, events, and retry history
- **Event Management**: Create, list, and replay events
- **Worker Monitoring**: List and inspect workers
- **Scheduling**: Manage cron triggers and scheduled runs
- **Multi-Profile Support**: Configure multiple environments (production, staging, etc.)
- **Flexible Output**: Table, JSON, and YAML output formats

## Installation

### From Source

```bash
cd hatchet-cli
pip install -e .
```

### Using pip (when published)

```bash
pip install hatchet-cli
```

## Quick Start

### 1. Initialize Configuration

```bash
hatchet config init
```

This will prompt you for your API token and save it securely.

### 2. Or Use Environment Variables

```bash
export HATCHET_API_TOKEN=your-api-token
export HATCHET_TENANT_ID=your-tenant-id
export HATCHET_BASE_URL=https://app.hatchet.run  # Optional, this is the default
```

### 3. Start Using the CLI

```bash
# List workflows
hatchet workflows list

# List recent runs
hatchet runs list

# Get quick status
hatchet status
```

## Commands

### Workflows

```bash
# List all workflows
hatchet workflows list

# Get workflow details
hatchet workflows get my-workflow

# Trigger a workflow
hatchet workflows trigger my-workflow --input '{"key": "value"}'

# Get workflow metrics
hatchet workflows metrics my-workflow

# Delete a workflow
hatchet workflows delete my-workflow
```

### Workflow Runs

```bash
# List all runs
hatchet runs list

# List with filters
hatchet runs list --status FAILED
hatchet runs list --workflow my-workflow
hatchet runs list --status RUNNING --status PENDING
hatchet runs list --created-after 2024-01-15T00:00:00Z

# Get run details
hatchet runs get <run-id>

# Get run input
hatchet runs input <run-id>

# Get run status
hatchet runs status <run-id>

# Cancel runs
hatchet runs cancel <run-id>
hatchet runs cancel run1 run2 run3

# Replay failed runs
hatchet runs replay <run-id>
hatchet runs replay run1 run2 run3

# Get run metrics
hatchet runs metrics --workflow my-workflow
```

### Step Runs

```bash
# Get step details
hatchet steps get <step-id>

# View step logs
hatchet steps logs <step-id>

# Get step events
hatchet steps events <step-id>

# Get retry history
hatchet steps archives <step-id>

# Rerun a failed step
hatchet steps rerun <step-id>

# Cancel a running step
hatchet steps cancel <step-id>
```

### Events

```bash
# List events
hatchet events list
hatchet events list --key user:signup

# Get event details
hatchet events get <event-id>

# Get event data/payload
hatchet events data <event-id>

# Create an event
hatchet events create user:signup --data '{"userId": "123"}'
hatchet events create order:created --data-file ./order.json

# Replay events
hatchet events replay <event-id>

# List event keys
hatchet events keys
```

### Workers

```bash
# List all workers
hatchet workers list

# Get worker details
hatchet workers get <worker-id>
```

### API Tokens

```bash
# List tokens
hatchet tokens list

# Create a token
hatchet tokens create --name "CI/CD Token"
hatchet tokens create --name "Temp Token" --expires 30d

# Revoke a token
hatchet tokens revoke <token-id>
```

### Cron Triggers

```bash
# List cron triggers
hatchet crons list

# Get cron details
hatchet crons get <cron-id>

# Create a cron trigger
hatchet crons create my-workflow --cron "0 9 * * *"  # Daily at 9am
hatchet crons create my-workflow --cron "*/5 * * * *" --name "Every 5 min"

# Delete a cron trigger
hatchet crons delete <cron-id>
```

### Scheduled Runs

```bash
# List scheduled runs
hatchet scheduled list

# Get scheduled run details
hatchet scheduled get <scheduled-id>

# Schedule a workflow run
hatchet scheduled create my-workflow --at "2024-01-15T10:00:00Z"
hatchet scheduled create my-workflow --at "+1h"  # In 1 hour
hatchet scheduled create my-workflow --at "+30m" --input '{"priority": "high"}'

# Delete a scheduled run
hatchet scheduled delete <scheduled-id>
```

### Tenant & User

```bash
# Get tenant info
hatchet tenant info

# List team members
hatchet tenant members

# Get metrics
hatchet tenant metrics

# Get current user
hatchet tenant user

# List your tenant memberships
hatchet tenant memberships
```

### Configuration

```bash
# Initialize configuration
hatchet config init

# Show current configuration
hatchet config show

# Set configuration values
hatchet config set output.format json
hatchet config set default_profile production

# Manage profiles
hatchet config profile list
hatchet config profile create staging --base-url https://staging.hatchet.run
hatchet config profile use production
hatchet config profile delete old-profile
```

## Global Options

| Option | Environment Variable | Description |
|--------|---------------------|-------------|
| `--api-token` | `HATCHET_API_TOKEN` | API token for authentication |
| `--tenant` | `HATCHET_TENANT_ID` | Tenant ID for operations |
| `--base-url` | `HATCHET_BASE_URL` | API base URL (default: https://app.hatchet.run) |
| `--profile` | - | Configuration profile to use |
| `--format` | - | Output format: table, json, yaml |
| `--no-color` | - | Disable colored output |
| `--help` | - | Show help message |
| `--version` | - | Show version |

## Output Formats

The CLI supports three output formats:

### Table (default)
```bash
hatchet workflows list
```
```
╭────────────────────────────────────────────────╮
│ Workflows (3 total)                            │
├──────────────────┬──────────────┬──────────────┤
│ Name             │ ID           │ Versions     │
├──────────────────┼──────────────┼──────────────┤
│ process-order    │ abc123...    │ 2            │
│ send-email       │ def456...    │ 1            │
│ daily-report     │ ghi789...    │ 3            │
╰──────────────────┴──────────────┴──────────────╯
```

### JSON
```bash
hatchet workflows list --format json
```
```json
[
  {
    "name": "process-order",
    "metadata": {"id": "abc123..."},
    ...
  }
]
```

### YAML
```bash
hatchet workflows list --format yaml
```
```yaml
- name: process-order
  metadata:
    id: abc123...
```

## Configuration File

Configuration is stored in `~/.hatchet/config.yaml`:

```yaml
default_profile: production

profiles:
  production:
    base_url: https://app.hatchet.run
    api_token: hatchet_pat_xxx
    tenant_id: tenant-uuid

  staging:
    base_url: https://staging.hatchet.run
    api_token: hatchet_pat_yyy
    tenant_id: tenant-uuid-staging

output:
  format: table
  color: true
```

## Filtering Runs

The `runs list` command supports powerful filtering:

```bash
# By status
hatchet runs list --status FAILED
hatchet runs list --status RUNNING --status PENDING

# By workflow
hatchet runs list --workflow my-workflow

# By time range
hatchet runs list --created-after 2024-01-15T00:00:00Z
hatchet runs list --created-before 2024-01-16T00:00:00Z
hatchet runs list --finished-after 2024-01-15T00:00:00Z

# By kind
hatchet runs list --kind CRON
hatchet runs list --kind SCHEDULED

# By metadata
hatchet runs list --metadata env:production
hatchet runs list --metadata priority:high --metadata region:us-east

# Combined filters
hatchet runs list --status FAILED --workflow my-workflow --created-after 2024-01-15T00:00:00Z

# Pagination
hatchet runs list --limit 20 --offset 40

# Ordering
hatchet runs list --order-by createdAt --order DESC
hatchet runs list --order-by finishedAt --order ASC
```

## Scripting

The CLI is designed to work well in scripts:

```bash
#!/bin/bash

# Get failed runs as JSON
failed_runs=$(hatchet runs list --status FAILED --format json)

# Replay all failed runs
echo "$failed_runs" | jq -r '.[].metadata.id' | xargs hatchet runs replay --yes

# Check workflow health
if ! hatchet health > /dev/null 2>&1; then
    echo "API is unhealthy!"
    exit 1
fi
```

## Aliases

The CLI is also available as `hctl`:

```bash
hctl workflows list
hctl runs list --status FAILED
```

## Requirements

- Python 3.9+
- Dependencies: click, httpx, rich, pyyaml, python-dateutil, tabulate

## Links

- [Hatchet Documentation](https://docs.hatchet.run)
- [Hatchet GitHub](https://github.com/hatchet-dev/hatchet)
- [API Reference](https://docs.hatchet.run/api-reference)

## License

MIT License - see LICENSE file for details.
