# Codex Session Tracker Prototype

A simple shell-based prototype for tracking Codex CLI sessions.

## Components

| Script | Purpose |
|--------|---------|
| `codex-tracked` | Wrapper for `codex` that enables tracking |
| `codex-dashboard` | Terminal UI showing all tracked sessions |
| `codex-tracker-clean` | Cleanup old tracking files |

## Installation

```bash
# Make scripts executable
chmod +x codex-tracked codex-dashboard codex-tracker-clean

# Copy to PATH (or symlink)
sudo cp codex-tracked codex-dashboard codex-tracker-clean /usr/local/bin/

# Or add alias to your shell config (~/.zshrc or ~/.bashrc)
alias cx='/path/to/codex-tracked'
```

## Usage

### Starting a Tracked Session

```bash
# Instead of: codex "your prompt"
# Use:
codex-tracked "your prompt"

# Or with the alias:
cx "your prompt"
```

### Viewing the Dashboard

```bash
# One-time view with interactive menu
codex-dashboard

# Watch mode (auto-refreshes every 2 seconds)
codex-dashboard --watch

# JSON output (for scripting)
codex-dashboard --json
```

### Cleaning Up Old Files

```bash
# Remove stopped sessions older than 24 hours (default)
codex-tracker-clean

# Remove sessions older than 6 hours
codex-tracker-clean --older-than 6

# Remove all stopped sessions
codex-tracker-clean --all
```

## Features

### Terminal Title

When you use `codex-tracked`, it will:
1. Set the terminal title to "🤖 Codex starting..."
2. After detecting your first message, summarize it with an LLM
3. Update the terminal title to "🤖 [Summary]"

This works with:
- iTerm2
- Terminal.app
- Most other terminals supporting OSC escape sequences

### LLM Summarization

The wrapper tries to summarize your request using:
1. `claude` CLI (if installed)
2. `llm` CLI (if installed)
3. Falls back to first 40 characters of your message

### Session Deeplinking

From the dashboard, you can jump directly to a session's terminal:
- **iTerm2**: Uses AppleScript to select the session
- **Terminal.app**: Uses AppleScript to focus the window
- Other terminals: Limited support (brings app to front)

### Notifications

When a session ends, you'll get a macOS notification with:
- The session summary
- The working directory

## File Structure

Sessions are tracked in `~/.codex-tracker/`:

```
~/.codex-tracker/
├── abc123-def456.json
├── xyz789-uvw012.json
└── ...
```

Each file contains:
```json
{
    "tracking_id": "abc123-def456",
    "pid": 12345,
    "cwd": "/Users/you/project",
    "start_time": "2025-01-15T10:30:00Z",
    "status": "running",
    "terminal": {
        "app": "iTerm.app",
        "session_id": "w0t0p0:12345678",
        "window_id": "123",
        "tty": "/dev/ttys003"
    },
    "session_file": "/Users/you/.codex/sessions/2025/01/15/rollout-...",
    "summary": "Fix auth bug in login",
    "last_activity": "2025-01-15T10:35:00Z"
}
```

## Requirements

- macOS (for AppleScript terminal integration)
- `jq` (JSON processing)
- `codex` CLI installed and configured
- Optional: `claude` or `llm` CLI for summarization

## Limitations

1. **macOS Only**: The AppleScript terminal integration only works on macOS
2. **Wrapper Required**: Only sessions started with `codex-tracked` are tracked
3. **LLM Dependency**: Summarization requires an LLM CLI to be installed
4. **Terminal Support**: Deeplinking only works with iTerm2 and Terminal.app

## Next Steps

This prototype demonstrates the core concepts. For a production-ready solution:

1. **Swift Menu Bar App**: See `CODEX_DASHBOARD_DESIGN.md` for the full native app design
2. **Background Service**: Use a LaunchAgent for persistent tracking
3. **WebSocket Server**: Replace file-based communication with sockets
4. **Rich UI**: SwiftUI popover with session details and controls
