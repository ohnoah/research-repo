# Codex CLI Session Monitoring Research

This document provides a comprehensive analysis of the Codex CLI codebase to understand the different mechanisms available for monitoring Codex sessions.

## Table of Contents

1. [Overview](#overview)
2. [Sessions Directory Structure](#sessions-directory-structure)
3. [RPC Server (app-server)](#rpc-server-app-server)
4. [Notify Hook](#notify-hook)
5. [Implementation Approaches](#implementation-approaches)
6. [Recommended Dashboard Architecture](#recommended-dashboard-architecture)

---

## Overview

The Codex CLI provides several mechanisms for monitoring sessions:

| Mechanism | Purpose | Real-time? | Access to Messages | Complexity |
|-----------|---------|------------|-------------------|------------|
| Sessions Directory | Persistent storage of all session data | No (polling) | Full access | Low |
| App-Server RPC | Control and monitor active sessions | Yes | Full access | High |
| Notify Hook | Get notified on turn completion | Yes | Partial (last message) | Low |
| File Watching | Detect new/modified session files | Semi | Full access | Medium |

---

## Sessions Directory Structure

### Location

Sessions are stored in JSONL files under `~/.codex/sessions/`:

```
~/.codex/sessions/
├── 2025/
│   ├── 01/
│   │   ├── 15/
│   │   │   ├── rollout-2025-01-15T10-30-45-<uuid>.jsonl
│   │   │   └── rollout-2025-01-15T14-22-11-<uuid>.jsonl
│   │   └── 16/
│   │       └── rollout-2025-01-16T09-15-33-<uuid>.jsonl
├── archived_sessions/  # Archived threads moved here
```

### File Format

Each session file is JSONL (JSON Lines). Each line is a `RolloutLine`:

```json
{
  "timestamp": "2025-01-15T10:30:45.123Z",
  "type": "session_meta",
  "payload": {
    "id": "uuid",
    "timestamp": "2025-01-15T10:30:45.123Z",
    "cwd": "/Users/user/project",
    "originator": "codex_cli_rs",
    "cli_version": "1.2.3",
    "instructions": null,
    "source": "cli",  // or "vscode", "exec", "mcp"
    "model_provider": "openai",
    "git": {
      "commit_hash": "abc123",
      "branch": "main",
      "repository_url": "https://github.com/user/repo"
    }
  }
}
```

### Session Sources

From `codex-rs/protocol/src/protocol.rs:1207-1219`:

- `Cli` - Interactive CLI session
- `VSCode` - VS Code extension
- `Exec` - Non-interactive `codex exec` command
- `Mcp` - MCP server mode
- `SubAgent` - Review or compact sub-agents

### RolloutItem Types

Each line can be one of:

1. **SessionMeta** - Session metadata (first line)
2. **ResponseItem** - Model responses, tool calls, etc.
3. **Compacted** - Summarized/compacted history
4. **TurnContext** - Turn-specific configuration
5. **EventMsg** - Events like UserMessage, AgentMessage, command execution, etc.

### Key Files for Sessions

- `codex-rs/core/src/rollout/mod.rs` - Main rollout module
- `codex-rs/core/src/rollout/list.rs` - Session listing with pagination
- `codex-rs/core/src/rollout/recorder.rs` - Session recording

### Listing Sessions Programmatically

From `list.rs:105-139`:

```rust
pub async fn get_conversations(
    codex_home: &Path,
    page_size: usize,
    cursor: Option<&Cursor>,
    allowed_sources: &[SessionSource],
    model_providers: Option<&[String]>,
    default_provider: &str,
) -> io::Result<ConversationsPage>
```

Returns `ConversationsPage` with:
- `items: Vec<ConversationItem>` - Session summaries
- `next_cursor: Option<Cursor>` - For pagination
- `num_scanned_files: usize`
- `reached_scan_cap: bool`

Each `ConversationItem` contains:
- `path: PathBuf` - Absolute path to rollout file
- `head: Vec<serde_json::Value>` - First ~10 records
- `created_at: Option<String>` - RFC3339 timestamp
- `updated_at: Option<String>` - Last modification time

### Reading Session History

From `recorder.rs:210-279`:

```rust
pub async fn get_rollout_history(path: &Path) -> std::io::Result<InitialHistory>
```

Returns the full history of a session including:
- `conversation_id` - Session UUID
- `history: Vec<RolloutItem>` - All items in the session

---

## RPC Server (app-server)

The app-server provides a JSON-RPC 2.0 interface over stdio for rich client integration.

### Starting the Server

```bash
codex app-server
```

### Protocol

- Bidirectional JSONL over stdio
- JSON-RPC 2.0 (without `"jsonrpc":"2.0"` header)

### Key Methods

From `codex-rs/app-server/README.md`:

#### Thread Management

| Method | Description |
|--------|-------------|
| `thread/start` | Create a new conversation thread |
| `thread/resume` | Resume an existing thread by ID |
| `thread/list` | List threads with pagination |
| `thread/archive` | Move thread to archived directory |

#### Turn Management

| Method | Description |
|--------|-------------|
| `turn/start` | Send user input, begin generation |
| `turn/interrupt` | Cancel running turn |
| `review/start` | Start a code review |

#### Other

| Method | Description |
|--------|-------------|
| `command/exec` | Run one-off command without thread |
| `model/list` | List available models |
| `config/read` | Get effective config |
| `account/read` | Get auth status |

### Events/Notifications

The server streams notifications for:

- `thread/started` - New thread created
- `turn/started` / `turn/completed` - Turn lifecycle
- `item/started` / `item/completed` - Individual items
- `item/agentMessage/delta` - Streaming agent output
- `item/commandExecution/outputDelta` - Command output
- Token usage, rate limits, errors, etc.

### Example: List Threads

Request:
```json
{ "method": "thread/list", "id": 1, "params": { "limit": 25 } }
```

Response:
```json
{
  "id": 1,
  "result": {
    "data": [
      {
        "id": "thr_abc123",
        "preview": "Fix the build",
        "modelProvider": "openai",
        "createdAt": 1730831111
      }
    ],
    "nextCursor": "opaque-token-or-null"
  }
}
```

### Key Files for App-Server

- `codex-rs/app-server/README.md` - Comprehensive protocol docs
- `codex-rs/app-server/src/message_processor.rs` - Request handling
- `codex-rs/app-server-protocol/src/protocol/v1.rs` - V1 protocol types
- `codex-rs/app-server-protocol/src/protocol/v2.rs` - V2 protocol types

---

## Notify Hook

The notify hook allows external programs to receive notifications when events occur.

### Configuration

In `~/.codex/config.toml`:

```toml
notify = ["python3", "/path/to/notify.py"]
```

### Notification Format

From `codex-rs/core/src/user_notification.rs:44-62`:

```json
{
  "type": "agent-turn-complete",
  "thread-id": "b5f6c1c2-1111-2222-3333-444455556666",
  "turn-id": "12345",
  "cwd": "/Users/example/project",
  "input-messages": ["Rename `foo` to `bar` and update the callsites."],
  "last-assistant-message": "Rename complete and verified `cargo build` succeeds."
}
```

### Currently Supported Types

Only `agent-turn-complete` is supported currently.

### How It Works

From `user_notification.rs:11-35`:

1. When a turn completes, `UserNotifier::notify()` is called
2. The notification is serialized to JSON
3. The configured program is spawned with the JSON as an argument
4. Fire-and-forget (doesn't wait for completion)

### Example Notification Script

```python
#!/usr/bin/env python3
import json
import subprocess
import sys

def main():
    if len(sys.argv) != 2:
        return 1

    notification = json.loads(sys.argv[1])

    if notification.get("type") == "agent-turn-complete":
        # Send desktop notification, update dashboard, etc.
        subprocess.run([
            "terminal-notifier",
            "-title", "Codex Turn Complete",
            "-message", notification.get("last-assistant-message", "Done"),
            "-group", f"codex-{notification.get('thread-id')}"
        ])

    return 0

if __name__ == "__main__":
    sys.exit(main())
```

---

## Implementation Approaches

### Approach 1: File System Monitoring (Simplest)

**Best for:** Getting an overview of all sessions

```python
import os
import json
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

CODEX_HOME = Path.home() / ".codex"
SESSIONS_DIR = CODEX_HOME / "sessions"

class SessionMonitor(FileSystemEventHandler):
    def on_modified(self, event):
        if event.src_path.endswith('.jsonl'):
            self.process_session(event.src_path)

    def on_created(self, event):
        if event.src_path.endswith('.jsonl'):
            self.process_session(event.src_path)

    def process_session(self, path):
        with open(path) as f:
            lines = f.readlines()

        # Parse session metadata (first line)
        meta = json.loads(lines[0])
        session_id = meta.get('payload', {}).get('meta', {}).get('id')
        cwd = meta.get('payload', {}).get('meta', {}).get('cwd')

        # Find last agent message
        last_message = None
        for line in reversed(lines):
            data = json.loads(line)
            if data.get('type') == 'event_msg':
                payload = data.get('payload', {})
                if payload.get('type') == 'agent_message':
                    last_message = payload.get('message')
                    break

        print(f"Session: {session_id}")
        print(f"  CWD: {cwd}")
        print(f"  Last message: {last_message}")

# Start watching
observer = Observer()
observer.schedule(SessionMonitor(), str(SESSIONS_DIR), recursive=True)
observer.start()
```

**Pros:**
- Simple to implement
- Access to full message history
- Works with any session (past and present)

**Cons:**
- Polling-based (not truly real-time)
- Need to parse JSONL files

### Approach 2: Notify Hook Integration

**Best for:** Real-time notifications of turn completion

Create a notify script that updates your dashboard:

```python
#!/usr/bin/env python3
import json
import sys
import requests  # or use sockets, etc.

def main():
    notification = json.loads(sys.argv[1])

    # Send to your dashboard
    requests.post("http://localhost:8080/codex-event", json={
        "type": notification["type"],
        "session_id": notification["thread-id"],
        "cwd": notification["cwd"],
        "last_message": notification.get("last-assistant-message"),
        "status": "completed"
    })

if __name__ == "__main__":
    sys.exit(main())
```

**Pros:**
- True real-time notifications
- Low overhead
- Official/supported mechanism

**Cons:**
- Only `agent-turn-complete` events
- Doesn't give you running sessions
- Requires configuration change

### Approach 3: App-Server RPC (Most Powerful)

**Best for:** Full control over sessions

```python
import json
import subprocess
import asyncio

class CodexRPC:
    def __init__(self):
        self.process = subprocess.Popen(
            ["codex", "app-server"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            text=True
        )
        self._id = 0

    def _send(self, method, params=None):
        self._id += 1
        msg = {"method": method, "id": self._id}
        if params:
            msg["params"] = params
        self.process.stdin.write(json.dumps(msg) + "\n")
        self.process.stdin.flush()
        return self._id

    def _recv(self):
        line = self.process.stdout.readline()
        return json.loads(line)

    def initialize(self):
        self._send("initialize", {
            "clientInfo": {
                "name": "session-monitor",
                "version": "1.0.0"
            }
        })
        return self._recv()

    def list_threads(self, limit=50):
        self._send("thread/list", {"limit": limit})
        return self._recv()

    def get_events(self):
        """Read streaming events"""
        while True:
            line = self.process.stdout.readline()
            if line:
                yield json.loads(line)

# Usage
rpc = CodexRPC()
rpc.initialize()

# List all threads
threads = rpc.list_threads()
for thread in threads["result"]["data"]:
    print(f"Thread: {thread['id']} - {thread['preview']}")

# Monitor events (for active sessions)
for event in rpc.get_events():
    if "method" in event:  # Notification
        print(f"Event: {event['method']}")
```

**Pros:**
- Full access to all functionality
- Real-time events
- Can control sessions (start, interrupt, etc.)

**Cons:**
- Complex to implement
- Need to manage process lifecycle
- Only monitors one "view" at a time

### Approach 4: Hybrid (Recommended)

Combine multiple approaches for best results:

1. **File watching** - Discover all sessions, get full history
2. **Notify hook** - Real-time turn completion events
3. **Process detection** - Find running Codex processes

```python
import os
import psutil

def find_codex_processes():
    """Find running Codex CLI processes"""
    codex_procs = []
    for proc in psutil.process_iter(['pid', 'name', 'cmdline', 'cwd']):
        try:
            if 'codex' in proc.name().lower():
                codex_procs.append({
                    'pid': proc.pid,
                    'cwd': proc.cwd(),
                    'cmdline': proc.cmdline()
                })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    return codex_procs
```

---

## Recommended Dashboard Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Codex Session Dashboard                   │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌──────────────────┐   ┌──────────────────────────────────┐ │
│  │ Active Sessions  │   │ Session Details                  │ │
│  │                  │   │                                  │ │
│  │ ● project-a      │   │ ID: abc-123-def                  │ │
│  │   Running        │   │ CWD: /Users/dev/project-a        │ │
│  │   5 turns        │   │ Started: 10:30 AM                │ │
│  │                  │   │ Model: gpt-5.1-codex             │ │
│  │ ○ project-b      │   │ Git: main @ abc1234              │ │
│  │   Completed      │   │                                  │ │
│  │   12 turns       │   │ ─────────────────────────────    │ │
│  │                  │   │ Latest Turn:                     │ │
│  │ ○ project-c      │   │ User: "Fix the authentication"   │ │
│  │   Stopped        │   │ Agent: "I've updated the auth    │ │
│  │   3 turns        │   │  module to use JWT tokens..."    │ │
│  └──────────────────┘   └──────────────────────────────────┘ │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### Components

1. **Session Scanner** (runs periodically)
   - Scans `~/.codex/sessions/` directory
   - Parses session metadata
   - Builds session list

2. **Notify Receiver** (webhook/socket server)
   - Receives events from notify hook
   - Updates session status in real-time
   - Triggers UI refresh

3. **Process Monitor** (optional)
   - Detects running Codex processes
   - Associates processes with sessions
   - Detects session termination

4. **Message Summarizer** (optional)
   - Uses LLM to summarize long conversations
   - Extracts key actions/decisions

### Data Model

```python
@dataclass
class CodexSession:
    id: str
    path: Path
    cwd: Path
    created_at: datetime
    updated_at: datetime
    source: str  # cli, vscode, exec
    model_provider: str
    git_info: Optional[GitInfo]
    status: str  # running, completed, stopped
    turns: List[Turn]

@dataclass
class Turn:
    id: str
    user_messages: List[str]
    agent_message: Optional[str]
    tool_calls: List[ToolCall]
    timestamp: datetime

@dataclass
class GitInfo:
    branch: Optional[str]
    commit_hash: Optional[str]
    repository_url: Optional[str]
```

---

## Caveats and Limitations

1. **No Running Session Detection via Files**
   - Files are written incrementally, but there's no "lock" file to indicate active sessions
   - Need to combine with process detection or notify hook

2. **Terminal Information Not Stored**
   - Session files don't record which terminal/TTY they're running in
   - Would need process inspection for this

3. **App-Server is Single-Instance**
   - Can't have multiple app-server instances for different sessions
   - Designed for IDE integration, not monitoring

4. **Notify Hook is Global**
   - One notify program for all sessions
   - Your script needs to handle routing

---

## Summary

For a session monitoring dashboard, the recommended approach is:

1. **Scan session files** for complete history and metadata
2. **Use notify hook** for real-time turn completion events
3. **Use process detection** to identify running vs stopped sessions
4. **Optionally use app-server** if you need to control sessions

The session files contain everything you need to summarize with LLMs - just parse the JSONL and extract the `agent_message` and `user_message` events.
