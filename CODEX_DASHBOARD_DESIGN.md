# Codex Session Dashboard - System Design

A performant local Mac app for monitoring and managing all Codex CLI sessions.

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [The Wrapper Script (`codex-tracked`)](#the-wrapper-script-codex-tracked)
4. [Terminal Integration](#terminal-integration)
5. [Swift Menu Bar App](#swift-menu-bar-app)
6. [Session State Management](#session-state-management)
7. [LLM Summarization](#llm-summarization)
8. [Notifications](#notifications)
9. [Implementation Plan](#implementation-plan)

---

## Overview

### Goals

1. **Know all running sessions** - Track every Codex session on the machine
2. **Real-time status** - What each session is doing, how long it's been running
3. **Detect stopped sessions** - Know when sessions end (reliably)
4. **Terminal integration** - Register terminal, auto-name windows, deeplink
5. **LLM summaries** - Automatically summarize what each session is working on
6. **Native Mac experience** - Performant menu bar app with notifications

### Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| App Framework | Swift/AppKit | Native performance, FSEvents, AppleScript |
| IPC Method | Unix Domain Socket | Low latency, no port conflicts, secure |
| State Storage | SQLite | Fast queries, atomic writes, robust |
| File Watching | FSEvents | Native macOS, efficient, coalesced |
| Process Monitoring | libproc + polling | Reliable, no kernel extensions needed |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         codex-tracked (wrapper)                          │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────┐  ┌───────────────┐  │
│  │ Terminal    │  │ Session      │  │ Title       │  │ Notify        │  │
│  │ Capture     │  │ Registration │  │ Manager     │  │ Forwarder     │  │
│  └──────┬──────┘  └──────┬───────┘  └──────┬──────┘  └───────┬───────┘  │
└─────────┼────────────────┼─────────────────┼─────────────────┼──────────┘
          │                │                 │                 │
          │    Unix Domain Socket            │                 │
          ▼                ▼                 ▼                 ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                    Codex Dashboard (Swift App)                           │
│                                                                          │
│  ┌──────────────────┐  ┌──────────────────┐  ┌────────────────────────┐ │
│  │ Socket Server    │  │ FSEvents Watcher │  │ Process Monitor        │ │
│  │ /tmp/codex-dash  │  │ ~/.codex/sessions│  │ (2s polling)           │ │
│  └────────┬─────────┘  └────────┬─────────┘  └───────────┬────────────┘ │
│           │                     │                        │              │
│           ▼                     ▼                        ▼              │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                     Session State Manager                         │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐               │   │
│  │  │ SQLite DB   │  │ Session     │  │ Summarizer  │               │   │
│  │  │             │  │ Correlator  │  │ Queue       │               │   │
│  │  └─────────────┘  └─────────────┘  └─────────────┘               │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│           │                                                             │
│           ▼                                                             │
│  ┌──────────────────────────────────────────────────────────────────┐   │
│  │                          UI Layer                                 │   │
│  │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐   │   │
│  │  │ Menu Bar    │  │ Popover     │  │ Notifications           │   │   │
│  │  │ Icon        │  │ Dashboard   │  │ (UNUserNotificationCtr) │   │   │
│  │  └─────────────┘  └─────────────┘  └─────────────────────────┘   │   │
│  └──────────────────────────────────────────────────────────────────┘   │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## The Wrapper Script (`codex-tracked`)

### Purpose

Wraps the `codex` command to:
1. Capture terminal identification before Codex starts
2. Register the session with the dashboard app
3. Watch for the first user message and trigger summarization
4. Set terminal title with the summary
5. Forward notify events to the dashboard
6. Report when the session ends

### Implementation

```bash
#!/bin/bash
# codex-tracked - Wrapper for codex that integrates with the dashboard

set -euo pipefail

# ============================================================================
# CONFIGURATION
# ============================================================================

SOCKET_PATH="/tmp/codex-dashboard.sock"
TRACKING_ID=$(uuidgen | tr '[:upper:]' '[:lower:]')
START_TIME=$(date +%s)

# ============================================================================
# TERMINAL DETECTION
# ============================================================================

detect_terminal_info() {
    local term_app="${TERM_PROGRAM:-unknown}"
    local term_id=""
    local window_id=""
    local tty_path=$(tty 2>/dev/null || echo "unknown")

    case "$term_app" in
        iTerm.app)
            term_id="${ITERM_SESSION_ID:-}"
            # Get window ID via AppleScript for deeplinking
            window_id=$(osascript -e 'tell application "iTerm2" to id of current window' 2>/dev/null || echo "")
            ;;
        Apple_Terminal)
            # Terminal.app uses window ID from environment
            term_id="${TERM_SESSION_ID:-$tty_path}"
            window_id=$(osascript -e 'tell application "Terminal" to id of front window' 2>/dev/null || echo "")
            ;;
        vscode)
            term_id="${VSCODE_INJECTION:-}${tty_path}"
            ;;
        *)
            term_id="$tty_path"
            ;;
    esac

    echo "$term_app|$term_id|$window_id|$tty_path"
}

TERMINAL_INFO=$(detect_terminal_info)
TERMINAL_APP=$(echo "$TERMINAL_INFO" | cut -d'|' -f1)
TERMINAL_ID=$(echo "$TERMINAL_INFO" | cut -d'|' -f2)
WINDOW_ID=$(echo "$TERMINAL_INFO" | cut -d'|' -f3)
TTY_PATH=$(echo "$TERMINAL_INFO" | cut -d'|' -f4)

# ============================================================================
# SOCKET COMMUNICATION
# ============================================================================

send_to_dashboard() {
    local message="$1"
    if [[ -S "$SOCKET_PATH" ]]; then
        echo "$message" | nc -U "$SOCKET_PATH" 2>/dev/null || true
    fi
}

# ============================================================================
# TERMINAL TITLE
# ============================================================================

set_terminal_title() {
    local title="$1"
    # OSC 0: Set window title
    printf '\033]0;%s\007' "$title"
    # OSC 1: Set tab/icon title (works in iTerm2)
    printf '\033]1;%s\007' "$title"
}

# ============================================================================
# SESSION WATCHING
# ============================================================================

# Find the most recently created session file
find_session_file() {
    local session_dir="$HOME/.codex/sessions"
    local latest=""
    local latest_time=0

    # Look for files created after we started
    while IFS= read -r -d '' file; do
        local file_time=$(stat -f %B "$file" 2>/dev/null || echo "0")
        if [[ "$file_time" -gt "$START_TIME" ]] && [[ "$file_time" -gt "$latest_time" ]]; then
            latest="$file"
            latest_time="$file_time"
        fi
    done < <(find "$session_dir" -name "*.jsonl" -type f -print0 2>/dev/null)

    echo "$latest"
}

# Watch for first user message and summarize
watch_for_first_message() {
    local max_wait=30  # seconds
    local waited=0
    local session_file=""

    # Wait for session file to appear
    while [[ -z "$session_file" ]] && [[ $waited -lt $max_wait ]]; do
        sleep 0.5
        session_file=$(find_session_file)
        ((waited++)) || true
    done

    if [[ -z "$session_file" ]]; then
        return
    fi

    # Notify dashboard of the session file
    send_to_dashboard "SESSION_FILE|$TRACKING_ID|$session_file"

    # Watch for first user message
    local found_message=""
    waited=0
    while [[ -z "$found_message" ]] && [[ $waited -lt 60 ]]; do
        # Look for user_message event in the file
        found_message=$(grep -m1 '"type":"user_message"' "$session_file" 2>/dev/null | head -1 || echo "")
        if [[ -z "$found_message" ]]; then
            sleep 0.5
            ((waited++)) || true
        fi
    done

    if [[ -n "$found_message" ]]; then
        # Extract message text and summarize
        local message_text=$(echo "$found_message" | jq -r '.payload.message // .message // "New session"' 2>/dev/null || echo "New session")

        # Call LLM to summarize (using claude CLI or llm CLI)
        local summary=""
        if command -v claude &>/dev/null; then
            summary=$(echo "Summarize this coding task in 5 words or less, no punctuation: $message_text" | claude --print 2>/dev/null | head -1 || echo "")
        elif command -v llm &>/dev/null; then
            summary=$(echo "Summarize this coding task in 5 words or less, no punctuation: $message_text" | llm 2>/dev/null | head -1 || echo "")
        fi

        if [[ -z "$summary" ]]; then
            # Fallback: first 30 chars of message
            summary="${message_text:0:30}"
        fi

        # Set terminal title
        set_terminal_title "🤖 $summary"

        # Notify dashboard
        send_to_dashboard "SUMMARY|$TRACKING_ID|$summary"
    fi
}

# ============================================================================
# CLEANUP
# ============================================================================

cleanup() {
    local exit_code=$?
    send_to_dashboard "STOPPED|$TRACKING_ID|$exit_code"
    exit $exit_code
}

trap cleanup EXIT INT TERM

# ============================================================================
# MAIN
# ============================================================================

# Register with dashboard
send_to_dashboard "REGISTER|$TRACKING_ID|$$|$(pwd)|$TERMINAL_APP|$TERMINAL_ID|$WINDOW_ID|$TTY_PATH"

# Start watching for first message in background
watch_for_first_message &
WATCHER_PID=$!

# Set initial title
set_terminal_title "🤖 Codex starting..."

# Create a custom notify script that forwards to our dashboard
NOTIFY_SCRIPT=$(mktemp)
cat > "$NOTIFY_SCRIPT" << 'NOTIFY_EOF'
#!/bin/bash
# Forward notification to dashboard
SOCKET_PATH="/tmp/codex-dashboard.sock"
if [[ -S "$SOCKET_PATH" ]]; then
    echo "NOTIFY|$1" | nc -U "$SOCKET_PATH" 2>/dev/null || true
fi
NOTIFY_EOF
chmod +x "$NOTIFY_SCRIPT"

# Check if user has existing notify config
EXISTING_NOTIFY=$(grep -E '^notify\s*=' ~/.codex/config.toml 2>/dev/null | head -1 || echo "")

# Run codex with our notify script
# We use a temporary config overlay
TEMP_CONFIG=$(mktemp)
if [[ -n "$EXISTING_NOTIFY" ]]; then
    # Chain with existing notify - create a wrapper
    CHAIN_SCRIPT=$(mktemp)
    cat > "$CHAIN_SCRIPT" << CHAIN_EOF
#!/bin/bash
# Run original notify
${EXISTING_NOTIFY#notify = }
# Forward to dashboard
echo "NOTIFY|\$1" | nc -U "$SOCKET_PATH" 2>/dev/null || true
CHAIN_EOF
    chmod +x "$CHAIN_SCRIPT"
    echo "notify = [\"$CHAIN_SCRIPT\"]" > "$TEMP_CONFIG"
else
    echo "notify = [\"$NOTIFY_SCRIPT\"]" > "$TEMP_CONFIG"
fi

# Run codex with config override
exec codex --config "notify=[\"$NOTIFY_SCRIPT\"]" "$@"
```

### Installation

```bash
# Install the wrapper
sudo cp codex-tracked /usr/local/bin/
sudo chmod +x /usr/local/bin/codex-tracked

# Create shell alias (add to ~/.zshrc or ~/.bashrc)
alias cx='codex-tracked'
```

---

## Terminal Integration

### Terminal Identification Matrix

| Terminal | Session ID Source | Window ID Method | Deeplink Method |
|----------|-------------------|------------------|-----------------|
| iTerm2 | `$ITERM_SESSION_ID` | AppleScript | `osascript` select session |
| Terminal.app | TTY path | AppleScript window ID | `osascript` activate window |
| VS Code | `$VSCODE_*` + TTY | Not available | Not supported |
| Warp | TTY path | Not available | Not supported |
| Kitty | `$KITTY_WINDOW_ID` | Kitty remote | `kitty @ focus-window` |
| Alacritty | TTY path | Not available | Not supported |

### Terminal Title Escape Sequences

```bash
# OSC 0: Window title (most terminals)
printf '\033]0;%s\007' "Title Here"

# OSC 1: Icon/tab name (iTerm2, some others)
printf '\033]1;%s\007' "Tab Title"

# OSC 2: Window title only
printf '\033]2;%s\007' "Window Title"

# iTerm2 specific - set badge
printf '\033]1337;SetBadgeFormat=%s\007' "$(echo -n "Badge" | base64)"

# iTerm2 specific - set tab color
printf '\033]6;1;bg;red;brightness;255\007'
```

### Deeplinking Implementation

```swift
// Swift code for terminal deeplinking

enum TerminalApp: String {
    case iTerm2 = "iTerm.app"
    case terminal = "Apple_Terminal"
    case unknown
}

struct TerminalSession {
    let app: TerminalApp
    let sessionId: String
    let windowId: String?
    let ttyPath: String
}

class TerminalDeeplinker {

    func focusSession(_ session: TerminalSession) {
        switch session.app {
        case .iTerm2:
            focusiTerm2Session(session.sessionId)
        case .terminal:
            focusTerminalWindow(session.ttyPath)
        case .unknown:
            // Best effort: bring app to front
            NSWorkspace.shared.launchApplication("Terminal")
        }
    }

    private func focusiTerm2Session(_ sessionId: String) {
        let script = """
        tell application "iTerm2"
            activate
            repeat with aWindow in windows
                repeat with aTab in tabs of aWindow
                    repeat with aSession in sessions of aTab
                        if unique id of aSession is "\(sessionId)" then
                            select aSession
                            return true
                        end if
                    end repeat
                end repeat
            end repeat
            return false
        end tell
        """

        runAppleScript(script)
    }

    private func focusTerminalWindow(_ ttyPath: String) {
        // Extract tty name (e.g., "ttys003" from "/dev/ttys003")
        let ttyName = URL(fileURLWithPath: ttyPath).lastPathComponent

        let script = """
        tell application "Terminal"
            activate
            repeat with aWindow in windows
                repeat with aTab in tabs of aWindow
                    if tty of aTab contains "\(ttyName)" then
                        set selected of aTab to true
                        set frontmost of aWindow to true
                        return true
                    end if
                end repeat
            end repeat
            return false
        end tell
        """

        runAppleScript(script)
    }

    private func runAppleScript(_ script: String) {
        var error: NSDictionary?
        if let scriptObject = NSAppleScript(source: script) {
            scriptObject.executeAndReturnError(&error)
            if let error = error {
                print("AppleScript error: \(error)")
            }
        }
    }
}
```

---

## Swift Menu Bar App

### Project Structure

```
CodexDashboard/
├── CodexDashboard.xcodeproj
├── Sources/
│   ├── App/
│   │   ├── AppDelegate.swift
│   │   ├── CodexDashboardApp.swift
│   │   └── MenuBarController.swift
│   ├── Core/
│   │   ├── SessionManager.swift
│   │   ├── SocketServer.swift
│   │   ├── FileWatcher.swift
│   │   ├── ProcessMonitor.swift
│   │   └── Database.swift
│   ├── Models/
│   │   ├── Session.swift
│   │   ├── Turn.swift
│   │   └── Terminal.swift
│   ├── Services/
│   │   ├── Summarizer.swift
│   │   ├── NotificationService.swift
│   │   └── TerminalDeeplinker.swift
│   └── UI/
│       ├── PopoverView.swift
│       ├── SessionRowView.swift
│       └── SessionDetailView.swift
└── Resources/
    ├── Assets.xcassets
    └── Info.plist
```

### Key Components

#### AppDelegate.swift

```swift
import Cocoa
import UserNotifications

@main
class AppDelegate: NSObject, NSApplicationDelegate {

    private var statusItem: NSStatusItem!
    private var popover: NSPopover!
    private var sessionManager: SessionManager!
    private var socketServer: SocketServer!
    private var fileWatcher: FileWatcher!
    private var processMonitor: ProcessMonitor!

    func applicationDidFinishLaunching(_ notification: Notification) {
        // Request notification permissions
        UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { _, _ in }

        // Initialize core services
        sessionManager = SessionManager()

        socketServer = SocketServer(path: "/tmp/codex-dashboard.sock")
        socketServer.delegate = sessionManager
        socketServer.start()

        fileWatcher = FileWatcher(path: "\(NSHomeDirectory())/.codex/sessions")
        fileWatcher.delegate = sessionManager
        fileWatcher.start()

        processMonitor = ProcessMonitor()
        processMonitor.delegate = sessionManager
        processMonitor.startPolling(interval: 2.0)

        // Set up menu bar
        setupMenuBar()
    }

    private func setupMenuBar() {
        statusItem = NSStatusBar.system.statusItem(withLength: NSStatusItem.variableLength)

        if let button = statusItem.button {
            button.image = NSImage(systemSymbolName: "terminal", accessibilityDescription: "Codex Dashboard")
            button.action = #selector(togglePopover)
        }

        popover = NSPopover()
        popover.contentSize = NSSize(width: 400, height: 500)
        popover.behavior = .transient
        popover.contentViewController = NSHostingController(
            rootView: PopoverView(sessionManager: sessionManager)
        )
    }

    @objc private func togglePopover() {
        if let button = statusItem.button {
            if popover.isShown {
                popover.performClose(nil)
            } else {
                popover.show(relativeTo: button.bounds, of: button, preferredEdge: .minY)
            }
        }
    }
}
```

#### SessionManager.swift

```swift
import Foundation
import Combine

class SessionManager: ObservableObject {

    @Published private(set) var sessions: [TrackedSession] = []

    private let database: Database
    private let summarizer: Summarizer
    private let notificationService: NotificationService
    private let deeplinker: TerminalDeeplinker

    private var sessionsByTrackingId: [UUID: TrackedSession] = [:]
    private var sessionsByPid: [Int32: TrackedSession] = [:]

    init() {
        database = Database()
        summarizer = Summarizer()
        notificationService = NotificationService()
        deeplinker = TerminalDeeplinker()

        // Load persisted sessions
        loadPersistedSessions()
    }

    // MARK: - Socket Server Events

    func handleRegister(
        trackingId: UUID,
        pid: Int32,
        cwd: String,
        terminalApp: String,
        terminalId: String,
        windowId: String?,
        ttyPath: String
    ) {
        let session = TrackedSession(
            trackingId: trackingId,
            pid: pid,
            cwd: cwd,
            startTime: Date(),
            status: .starting,
            terminal: TerminalInfo(
                app: TerminalApp(rawValue: terminalApp) ?? .unknown,
                sessionId: terminalId,
                windowId: windowId,
                ttyPath: ttyPath
            )
        )

        sessionsByTrackingId[trackingId] = session
        sessionsByPid[pid] = session

        DispatchQueue.main.async {
            self.sessions.append(session)
            self.sessions.sort { $0.startTime > $1.startTime }
        }

        database.insertSession(session)
    }

    func handleSessionFile(trackingId: UUID, path: String) {
        guard var session = sessionsByTrackingId[trackingId] else { return }

        session.rolloutPath = path
        session.status = .running

        // Parse session ID from file
        if let sessionId = parseSessionId(from: path) {
            session.sessionId = sessionId
        }

        updateSession(session)
    }

    func handleSummary(trackingId: UUID, summary: String) {
        guard var session = sessionsByTrackingId[trackingId] else { return }

        session.summary = summary
        updateSession(session)
    }

    func handleNotify(json: String) {
        guard let data = json.data(using: .utf8),
              let notification = try? JSONDecoder().decode(CodexNotification.self, from: data) else {
            return
        }

        // Find session by thread ID
        guard var session = sessions.first(where: { $0.sessionId?.uuidString == notification.threadId }) else {
            return
        }

        session.lastActivity = Date()
        session.turnCount += 1
        session.lastMessage = notification.lastAssistantMessage

        updateSession(session)
    }

    func handleStopped(trackingId: UUID, exitCode: Int32) {
        guard var session = sessionsByTrackingId[trackingId] else { return }

        session.status = .stopped
        session.endTime = Date()
        session.exitCode = exitCode

        updateSession(session)

        // Send notification
        notificationService.sendStoppedNotification(for: session)
    }

    // MARK: - Process Monitor Events

    func processTerminated(pid: Int32) {
        guard var session = sessionsByPid[pid] else { return }

        if session.status != .stopped {
            session.status = .stopped
            session.endTime = Date()

            updateSession(session)
            notificationService.sendStoppedNotification(for: session)
        }
    }

    // MARK: - File Watcher Events

    func sessionFileModified(path: String) {
        // Find session with this path
        guard var session = sessions.first(where: { $0.rolloutPath == path }) else {
            return
        }

        session.lastActivity = Date()

        // Parse latest events from file
        parseLatestEvents(for: &session, from: path)

        updateSession(session)
    }

    // MARK: - Actions

    func focusSession(_ session: TrackedSession) {
        deeplinker.focusSession(session.terminal)
    }

    // MARK: - Private

    private func updateSession(_ session: TrackedSession) {
        sessionsByTrackingId[session.trackingId] = session
        if let pid = session.pid {
            sessionsByPid[pid] = session
        }

        DispatchQueue.main.async {
            if let index = self.sessions.firstIndex(where: { $0.trackingId == session.trackingId }) {
                self.sessions[index] = session
            }
        }

        database.updateSession(session)
    }

    private func parseSessionId(from path: String) -> UUID? {
        // Parse first line of JSONL for session ID
        guard let data = FileManager.default.contents(atPath: path),
              let firstLine = String(data: data, encoding: .utf8)?.components(separatedBy: "\n").first,
              let json = try? JSONSerialization.jsonObject(with: Data(firstLine.utf8)) as? [String: Any],
              let payload = json["payload"] as? [String: Any],
              let meta = payload["meta"] as? [String: Any],
              let idString = meta["id"] as? String else {
            return nil
        }
        return UUID(uuidString: idString)
    }

    private func parseLatestEvents(for session: inout TrackedSession, from path: String) {
        // Read last few lines of file for latest events
        // This is called on file change to update turn status
        guard let data = FileManager.default.contents(atPath: path),
              let content = String(data: data, encoding: .utf8) else {
            return
        }

        let lines = content.components(separatedBy: "\n").suffix(10)

        for line in lines.reversed() {
            guard !line.isEmpty,
                  let json = try? JSONSerialization.jsonObject(with: Data(line.utf8)) as? [String: Any],
                  let type = json["type"] as? String else {
                continue
            }

            switch type {
            case "event_msg":
                if let payload = json["payload"] as? [String: Any],
                   let eventType = payload["type"] as? String {
                    switch eventType {
                    case "task_complete":
                        session.status = .waiting
                    case "task_started":
                        session.status = .running
                    default:
                        break
                    }
                }
            default:
                break
            }
        }
    }
}
```

#### SocketServer.swift

```swift
import Foundation
import Network

class SocketServer {

    weak var delegate: SessionManager?

    private let path: String
    private var listener: NWListener?
    private let queue = DispatchQueue(label: "codex.dashboard.socket")

    init(path: String) {
        self.path = path
    }

    func start() {
        // Remove existing socket file
        try? FileManager.default.removeItem(atPath: path)

        do {
            let params = NWParameters()
            params.defaultProtocolStack.transportProtocol = NWProtocolTCP.Options()
            params.requiredLocalEndpoint = NWEndpoint.unix(path: path)

            listener = try NWListener(using: params)

            listener?.newConnectionHandler = { [weak self] connection in
                self?.handleConnection(connection)
            }

            listener?.start(queue: queue)

            // Set permissions so any user can connect
            chmod(path, 0o777)

        } catch {
            print("Failed to start socket server: \(error)")
        }
    }

    private func handleConnection(_ connection: NWConnection) {
        connection.start(queue: queue)

        connection.receive(minimumIncompleteLength: 1, maximumLength: 65536) { [weak self] data, _, _, _ in
            if let data = data, let message = String(data: data, encoding: .utf8) {
                self?.handleMessage(message.trimmingCharacters(in: .whitespacesAndNewlines))
            }
            connection.cancel()
        }
    }

    private func handleMessage(_ message: String) {
        let parts = message.components(separatedBy: "|")
        guard let command = parts.first else { return }

        switch command {
        case "REGISTER":
            guard parts.count >= 8,
                  let trackingId = UUID(uuidString: parts[1]),
                  let pid = Int32(parts[2]) else { return }

            delegate?.handleRegister(
                trackingId: trackingId,
                pid: pid,
                cwd: parts[3],
                terminalApp: parts[4],
                terminalId: parts[5],
                windowId: parts[6].isEmpty ? nil : parts[6],
                ttyPath: parts[7]
            )

        case "SESSION_FILE":
            guard parts.count >= 3,
                  let trackingId = UUID(uuidString: parts[1]) else { return }
            delegate?.handleSessionFile(trackingId: trackingId, path: parts[2])

        case "SUMMARY":
            guard parts.count >= 3,
                  let trackingId = UUID(uuidString: parts[1]) else { return }
            delegate?.handleSummary(trackingId: trackingId, summary: parts[2])

        case "NOTIFY":
            guard parts.count >= 2 else { return }
            delegate?.handleNotify(json: parts[1])

        case "STOPPED":
            guard parts.count >= 3,
                  let trackingId = UUID(uuidString: parts[1]),
                  let exitCode = Int32(parts[2]) else { return }
            delegate?.handleStopped(trackingId: trackingId, exitCode: exitCode)

        default:
            print("Unknown command: \(command)")
        }
    }
}
```

#### ProcessMonitor.swift

```swift
import Foundation

class ProcessMonitor {

    weak var delegate: SessionManager?

    private var timer: Timer?
    private var knownPids: Set<Int32> = []

    func startPolling(interval: TimeInterval) {
        timer = Timer.scheduledTimer(withTimeInterval: interval, repeats: true) { [weak self] _ in
            self?.poll()
        }
    }

    func stopPolling() {
        timer?.invalidate()
        timer = nil
    }

    private func poll() {
        // Get all codex processes
        let runningCodexPids = findCodexProcesses()

        // Check for terminated processes
        for pid in knownPids {
            if !runningCodexPids.contains(pid) {
                delegate?.processTerminated(pid: pid)
            }
        }

        knownPids = runningCodexPids
    }

    private func findCodexProcesses() -> Set<Int32> {
        var pids = Set<Int32>()

        // Use libproc to get process list
        var buffer = [pid_t](repeating: 0, count: 1024)
        let count = proc_listpids(UInt32(PROC_ALL_PIDS), 0, &buffer, Int32(buffer.count * MemoryLayout<pid_t>.size))

        let pidCount = Int(count) / MemoryLayout<pid_t>.size

        for i in 0..<pidCount {
            let pid = buffer[i]
            if pid == 0 { continue }

            var pathBuffer = [CChar](repeating: 0, count: Int(PROC_PIDPATHINFO_MAXSIZE))
            let pathLength = proc_pidpath(pid, &pathBuffer, UInt32(pathBuffer.count))

            if pathLength > 0 {
                let path = String(cString: pathBuffer)
                if path.contains("codex") && !path.contains("codex-dashboard") {
                    pids.insert(pid)
                }
            }
        }

        return pids
    }
}
```

#### FileWatcher.swift

```swift
import Foundation

class FileWatcher {

    weak var delegate: SessionManager?

    private let path: String
    private var eventStream: FSEventStreamRef?
    private let queue = DispatchQueue(label: "codex.dashboard.fswatcher")

    init(path: String) {
        self.path = path
    }

    func start() {
        var context = FSEventStreamContext()
        context.info = Unmanaged.passUnretained(self).toOpaque()

        let callback: FSEventStreamCallback = { streamRef, clientCallBackInfo, numEvents, eventPaths, eventFlags, eventIds in
            guard let clientCallBackInfo = clientCallBackInfo else { return }
            let watcher = Unmanaged<FileWatcher>.fromOpaque(clientCallBackInfo).takeUnretainedValue()

            let paths = unsafeBitCast(eventPaths, to: NSArray.self) as! [String]

            for path in paths {
                if path.hasSuffix(".jsonl") {
                    watcher.delegate?.sessionFileModified(path: path)
                }
            }
        }

        eventStream = FSEventStreamCreate(
            nil,
            callback,
            &context,
            [path] as CFArray,
            FSEventStreamEventId(kFSEventStreamEventIdSinceNow),
            0.5,  // Latency in seconds
            UInt32(kFSEventStreamCreateFlagFileEvents | kFSEventStreamCreateFlagUseCFTypes)
        )

        if let stream = eventStream {
            FSEventStreamSetDispatchQueue(stream, queue)
            FSEventStreamStart(stream)
        }
    }

    func stop() {
        if let stream = eventStream {
            FSEventStreamStop(stream)
            FSEventStreamInvalidate(stream)
            FSEventStreamRelease(stream)
        }
        eventStream = nil
    }
}
```

---

## Session State Management

### Data Model

```swift
struct TrackedSession: Identifiable, Codable {
    let id: UUID { trackingId }

    // Tracking info
    let trackingId: UUID
    var sessionId: UUID?
    var rolloutPath: String?

    // Process info
    var pid: Int32?
    let cwd: String
    let startTime: Date
    var endTime: Date?
    var exitCode: Int32?

    // Status
    var status: SessionStatus
    var lastActivity: Date

    // Content
    var summary: String?
    var lastMessage: String?
    var turnCount: Int = 0

    // Terminal
    var terminal: TerminalInfo

    // Computed
    var duration: TimeInterval {
        (endTime ?? Date()).timeIntervalSince(startTime)
    }

    var formattedDuration: String {
        let formatter = DateComponentsFormatter()
        formatter.unitsStyle = .abbreviated
        formatter.allowedUnits = [.hour, .minute, .second]
        return formatter.string(from: duration) ?? ""
    }
}

enum SessionStatus: String, Codable {
    case starting   // Just registered, waiting for session file
    case running    // Active turn in progress
    case waiting    // Turn complete, waiting for user input
    case stopped    // Process ended
}

struct TerminalInfo: Codable {
    let app: TerminalApp
    let sessionId: String
    let windowId: String?
    let ttyPath: String
}

enum TerminalApp: String, Codable {
    case iTerm2 = "iTerm.app"
    case terminal = "Apple_Terminal"
    case vscode = "vscode"
    case unknown
}
```

### SQLite Schema

```sql
CREATE TABLE sessions (
    tracking_id TEXT PRIMARY KEY,
    session_id TEXT,
    rollout_path TEXT,
    pid INTEGER,
    cwd TEXT NOT NULL,
    start_time REAL NOT NULL,
    end_time REAL,
    exit_code INTEGER,
    status TEXT NOT NULL,
    last_activity REAL NOT NULL,
    summary TEXT,
    last_message TEXT,
    turn_count INTEGER DEFAULT 0,
    terminal_app TEXT,
    terminal_session_id TEXT,
    terminal_window_id TEXT,
    terminal_tty TEXT
);

CREATE INDEX idx_sessions_status ON sessions(status);
CREATE INDEX idx_sessions_start_time ON sessions(start_time DESC);
```

---

## LLM Summarization

### Strategy

1. **Initial Summary**: When first user message is detected
   - Extract message text from JSONL
   - Call LLM with prompt: "Summarize this coding task in 5 words or less"
   - Cache the summary

2. **Updated Summary** (optional): After significant progress
   - Triggered after N turns or on explicit request
   - Summarize the overall progress

### Implementation

```swift
class Summarizer {

    private let queue = DispatchQueue(label: "codex.dashboard.summarizer")
    private var cache: [UUID: String] = [:]

    func summarize(message: String, completion: @escaping (String?) -> Void) {
        queue.async {
            let prompt = "Summarize this coding task in 5 words or less, no punctuation: \(message)"

            // Try claude CLI first
            if let summary = self.callCLI(command: "claude", args: ["--print"], input: prompt) {
                completion(summary)
                return
            }

            // Fallback to llm CLI
            if let summary = self.callCLI(command: "llm", args: [], input: prompt) {
                completion(summary)
                return
            }

            // Fallback: truncate message
            let truncated = String(message.prefix(30))
            completion(truncated)
        }
    }

    private func callCLI(command: String, args: [String], input: String) -> String? {
        let process = Process()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/env")
        process.arguments = [command] + args

        let inputPipe = Pipe()
        let outputPipe = Pipe()
        process.standardInput = inputPipe
        process.standardOutput = outputPipe
        process.standardError = FileHandle.nullDevice

        do {
            try process.run()

            inputPipe.fileHandleForWriting.write(Data(input.utf8))
            inputPipe.fileHandleForWriting.closeFile()

            process.waitUntilExit()

            if process.terminationStatus == 0 {
                let data = outputPipe.fileHandleForReading.readDataToEndOfFile()
                if let output = String(data: data, encoding: .utf8) {
                    return output.trimmingCharacters(in: .whitespacesAndNewlines)
                        .components(separatedBy: "\n").first
                }
            }
        } catch {
            return nil
        }

        return nil
    }
}
```

---

## Notifications

### Types

1. **Session Stopped** - When a session ends (via notify or process monitor)
2. **Turn Complete** - When a turn finishes (forwarded from notify hook)
3. **Approval Needed** - When Codex needs user input (if detectable)

### Implementation

```swift
import UserNotifications

class NotificationService {

    func sendStoppedNotification(for session: TrackedSession) {
        let content = UNMutableNotificationContent()
        content.title = "Codex Session Ended"
        content.body = session.summary ?? "Session in \(session.cwd)"
        content.sound = .default

        // Add action to open terminal
        content.categoryIdentifier = "SESSION_STOPPED"
        content.userInfo = [
            "trackingId": session.trackingId.uuidString,
            "action": "focus"
        ]

        let request = UNNotificationRequest(
            identifier: session.trackingId.uuidString,
            content: content,
            trigger: nil
        )

        UNUserNotificationCenter.current().add(request)
    }

    func sendTurnCompleteNotification(for session: TrackedSession, message: String?) {
        let content = UNMutableNotificationContent()
        content.title = session.summary ?? "Codex"
        content.body = message ?? "Turn completed"
        content.sound = .default
        content.categoryIdentifier = "TURN_COMPLETE"
        content.userInfo = [
            "trackingId": session.trackingId.uuidString,
            "action": "focus"
        ]

        let request = UNNotificationRequest(
            identifier: "\(session.trackingId.uuidString)-turn",
            content: content,
            trigger: nil
        )

        UNUserNotificationCenter.current().add(request)
    }
}
```

---

## Implementation Plan

### Phase 1: Core Infrastructure (Week 1)

1. **Wrapper Script**
   - [ ] Terminal detection
   - [ ] Registration with socket
   - [ ] Session file detection
   - [ ] Cleanup on exit

2. **Swift App Skeleton**
   - [ ] Menu bar icon
   - [ ] Basic popover UI
   - [ ] Unix domain socket server

### Phase 2: Session Tracking (Week 2)

1. **Session Manager**
   - [ ] SQLite database
   - [ ] State management
   - [ ] Session correlation

2. **File Watcher**
   - [ ] FSEvents integration
   - [ ] JSONL parsing
   - [ ] Event extraction

3. **Process Monitor**
   - [ ] libproc integration
   - [ ] Polling loop
   - [ ] Termination detection

### Phase 3: Terminal Integration (Week 3)

1. **Title Setting**
   - [ ] OSC escape sequences
   - [ ] iTerm2 specifics
   - [ ] Terminal.app support

2. **Deeplinking**
   - [ ] AppleScript for iTerm2
   - [ ] AppleScript for Terminal.app
   - [ ] Click handling in UI

3. **LLM Summarization**
   - [ ] CLI integration
   - [ ] Summary caching
   - [ ] Fallback handling

### Phase 4: Polish (Week 4)

1. **Notifications**
   - [ ] Session stopped
   - [ ] Turn complete
   - [ ] Action handling

2. **UI Refinement**
   - [ ] Session list design
   - [ ] Detail view
   - [ ] Status indicators

3. **Reliability**
   - [ ] Error handling
   - [ ] Reconnection logic
   - [ ] Orphan session discovery

---

## Open Questions

1. **Orphan Sessions**: How to handle Codex sessions started without the wrapper?
   - Option A: Periodic scan of process list + session files
   - Option B: Require wrapper usage
   - Option C: Hybrid approach

2. **Multi-User Support**: Should the dashboard support multiple users?
   - Probably not needed for personal use
   - Socket permissions handle security

3. **Remote Sessions**: What about SSH sessions running Codex?
   - Out of scope for v1
   - Could add SSH forwarding later

4. **VS Code Integration**: The VS Code extension uses app-server
   - Could detect VS Code terminals differently
   - Or focus on CLI usage only

---

## Appendix: Useful References

- [FSEvents Programming Guide](https://developer.apple.com/library/archive/documentation/Darwin/Conceptual/FSEvents_ProgGuide/)
- [libproc Reference](https://opensource.apple.com/source/xnu/xnu-1504.7.4/bsd/sys/proc_info.h)
- [iTerm2 Scripting](https://iterm2.com/documentation-scripting.html)
- [OSC Escape Sequences](https://invisible-island.net/xterm/ctlseqs/ctlseqs.html)
- [NWListener Unix Socket](https://developer.apple.com/documentation/network/nwlistener)
