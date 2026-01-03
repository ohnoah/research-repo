# Helicone CLI

A command-line interface for fetching data from Helicone. Query requests, sessions, and view metrics directly from your terminal.

## Installation

```bash
# From source
cd helicone-cli
npm install
npm run build
node dist/index.js --help

# Or link globally
npm link
helicone --help
```

## Authentication

The CLI supports three authentication methods (in order of precedence):

1. **CLI flag**: `--api-key sk-helicone-...`
2. **Environment variable**: `HELICONE_API_KEY=sk-helicone-...`
3. **Stored credentials**: `helicone auth login`

```bash
# Store credentials for future use
helicone auth login --api-key sk-helicone-...

# Check auth status
helicone auth status

# Remove stored credentials
helicone auth logout
```

## Commands

### Requests

Query and export LLM request data.

```bash
# List recent requests (last 7 days, 25 results)
helicone requests list

# List with filters
helicone requests list --model gpt-4o --status 200 --since 24h

# List with custom fields
helicone requests list --fields request_id,model,cost,latency_ms

# Filter by properties
helicone requests list -p environment=production -p user_type=premium

# Output as JSON
helicone requests list --format json

# Get single request (shows summary by default)
helicone requests get <request-id>

# View just the chat messages (formatted nicely)
helicone requests get <request-id> --show messages

# View request metadata (timing, tokens, cost)
helicone requests get <request-id> --show metadata

# View specific sections
helicone requests get <request-id> --show request    # Request body
helicone requests get <request-id> --show response   # Response body
helicone requests get <request-id> --show properties # Custom properties
helicone requests get <request-id> --show scores     # Evaluation scores

# Extract specific fields (jq-like path syntax)
helicone requests get <request-id> --extract response_body.choices[0].message.content
helicone requests get <request-id> --extract request_body.messages

# Get raw JSON (full request object)
helicone requests get <request-id> --raw

# Export to file
helicone requests export --since 30d --format jsonl -o requests.jsonl

# Export with bodies included
helicone requests export --since 7d --include-body -o full-export.jsonl

# See available fields
helicone requests fields
```

#### Request Filters

| Filter | Description | Example |
|--------|-------------|---------|
| `--since` | Start date (ISO or relative) | `--since 7d`, `--since 2024-01-01` |
| `--until` | End date | `--until 2024-01-31` |
| `--model` | Model name | `--model gpt-4o` |
| `--status` | HTTP status code | `--status 200` |
| `--user-id` | Your app's user ID | `--user-id user_123` |
| `--property` | Custom property | `-p key=value` |
| `--min-cost` | Minimum cost (USD) | `--min-cost 0.01` |
| `--max-cost` | Maximum cost (USD) | `--max-cost 1.00` |
| `--min-latency` | Minimum latency (ms) | `--min-latency 1000` |
| `--max-latency` | Maximum latency (ms) | `--max-latency 5000` |
| `--cached` | Only cached requests | `--cached` |

#### Viewing Single Requests

The `get` command provides flexible options for viewing request data:

| Option | Description |
|--------|-------------|
| `--show summary` | Clean summary with key info (default) |
| `--show messages` | Formatted chat messages with role colors |
| `--show request` | Raw request body JSON |
| `--show response` | Raw response body JSON |
| `--show metadata` | Timing, tokens, cost breakdown |
| `--show properties` | Custom properties |
| `--show scores` | Evaluation scores |
| `--show all` | Full JSON object |
| `--extract <path>` | Extract specific field using dot notation |
| `--raw` | Alias for `--show all --format json` |

### Sessions

Query session/trace data (grouped requests).

```bash
# List sessions
helicone sessions list --since 7d

# Search by name
helicone sessions list --search "chat-session"

# Get session details with requests
helicone sessions get <session-id> --include-requests

# Export sessions
helicone sessions export --since 30d -o sessions.jsonl
```

### Metrics

View aggregate statistics.

```bash
# Summary metrics
helicone metrics summary --since 30d

# Cost breakdown by model
helicone metrics cost --by model

# Cost breakdown by day
helicone metrics cost --by day --since 7d

# Error analysis
helicone metrics errors --since 7d
```

## Output Formats

All list/export commands support multiple output formats:

| Format | Flag | Description |
|--------|------|-------------|
| Table | `--format table` | Pretty-printed terminal table (default for list) |
| JSON | `--format json` | Pretty-printed JSON array |
| JSONL | `--format jsonl` | One JSON object per line (default for export) |
| CSV | `--format csv` | Comma-separated values |

## Field Selection

Use `--fields` to specify which fields to display/export:

```bash
# Only show specific fields
helicone requests list --fields request_id,model,cost

# See all available fields
helicone requests fields
```

## Default Behaviors

- **Time range**: Last 7 days by default (`--since 7d`)
- **Limit**: 25 results for list, unlimited for export
- **Bodies**: Request/response bodies are NOT included by default (use `--include-body`)
- **Sort**: Descending by creation time (newest first)

## Region Support

For EU-hosted data, use the `--region` flag:

```bash
helicone requests list --region eu
```

Or set during login:

```bash
helicone auth login --region eu
```

## Examples

```bash
# Find expensive requests
helicone requests list --min-cost 0.10 --since 24h

# Check error rate
helicone metrics errors --since 7d

# Export GPT-4 requests for analysis
helicone requests export --model gpt-4 --since 30d --format csv -o gpt4-requests.csv

# View session conversation
helicone sessions get sess_abc123 --include-requests --format json

# View formatted chat messages from a request
helicone requests get req_abc123 --show messages

# Extract just the assistant's response
helicone requests get req_abc123 --extract response_body.choices[0].message.content

# Quick look at timing and cost
helicone requests get req_abc123 --show metadata
```

## Development

```bash
# Install dependencies
npm install

# Build
npm run build

# Type check
npm run typecheck

# Watch mode
npm run dev
```

## License

MIT
