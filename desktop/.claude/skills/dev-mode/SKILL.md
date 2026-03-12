---
name: dev-mode
description: "Customize the OMI Desktop app by modifying Swift source code and local SQLite database. Use when the user asks to change app behavior, UI, add features, or modify how data is displayed. Only active when Dev Mode is enabled in settings."
allowed-tools: Bash, Read, Write, Edit, Glob, Grep
---

# Dev Mode — App Customization

You can modify the OMI Desktop app's source code and rebuild it for the user. The app is a Swift/SwiftUI macOS app with a local SQLite database (GRDB).

## What You Can Modify

### UNLOCKED — Full Read/Write Access

**UI & Features** (`Desktop/Sources/`):
- `MainWindow/` — All window and page views
- `Chat/` — Chat UI components
- `Providers/` — ViewModels and data providers
- `Rewind/Views/` — Screenshot and timeline views
- Any `.swift` file under `Desktop/Sources/` unless listed as locked below

**Local Database** (`Desktop/Sources/Rewind/Core/`):
- Add new GRDB migrations in `RewindDatabase.swift` (append at the end of `setupMigrations()`)
- Add new model structs conforming to `Codable, FetchableRecord, PersistableRecord`
- Add new Storage actors for custom data
- Prefix custom tables with `custom_` to avoid conflicts with existing tables

**App Configuration**:
- `Info.plist` values (via build scripts)
- Menu bar items
- Navigation structure

### READ-ONLY — Can Read, Cannot Modify

These files are critical infrastructure. Read them to understand how things work, but do not modify:

- `APIClient.swift` — Backend API communication (endpoints are fixed)
- `AuthService.swift` — Firebase authentication
- `AgentSyncService.swift` — Sync engine between local SQLite and backend
- `ActionItemStorage.swift`, `MemoryStorage.swift`, `TranscriptionStorage.swift` — Backend sync logic
- `ClaudeAgentBridge.swift` — AI chat bridge (modifying this breaks the chat)
- `agent-bridge/` — Node.js bridge code
- `Backend-Rust/` — Rust backend (runs on Cloud Run, not on user's machine)

### OFF-LIMITS — Cannot Read or Modify

- `.env`, `.env.app` — API keys and secrets
- `google-credentials.json`, `GoogleService-Info.plist` — Firebase credentials
- `embedded.provisionprofile`, `embedded-dev.provisionprofile` — Signing profiles

## Workspace Location

The source code workspace is at:
```
~/Library/Application Support/Omi/workspace/omi-desktop/
```

Secrets (API keys, certificates) are stored separately at:
```
~/Library/Application Support/Omi/workspace/.secrets/
```
The AI CANNOT access the `.secrets/` directory.

## How to Build After Changes

After modifying source files, build and launch with:

```bash
# Full build + bundle + sign + launch (10-30 seconds incremental)
~/Library/Application\ Support/Omi/workspace/omi-desktop/scripts/dev-build.sh --launch
```

Or build without launching:
```bash
~/Library/Application\ Support/Omi/workspace/omi-desktop/scripts/dev-build.sh
```

The build script automatically:
- Compiles Swift from the workspace (incremental, fast)
- Creates the app bundle with all resources
- Copies API keys and certificates from the installed app
- Signs with available developer identity (or ad-hoc)
- Launches the custom app

**First build** takes 3-5 minutes (compiles all dependencies). Subsequent builds are incremental and fast.

**IMPORTANT**: Before building, always check that Xcode Command Line Tools are installed:
```bash
xcode-select -p  # Should return a path, not an error
```

## Local SQLite Database

The app uses GRDB (SQLite) for local data. The database is at:
```
~/Library/Application Support/Omi/users/{userId}/omi.db
```

### Existing Tables (READ from these, do NOT modify their schema)

- `screenshots` — Screen captures with OCR text
- `transcription_sessions` — Recording sessions (conversations)
- `transcription_segments` — Individual transcript segments
- `action_items` — Tasks/to-dos (synced with backend)
- `staged_tasks` — AI-proposed tasks awaiting promotion
- `memories` — Extracted memories (synced with backend)
- `focus_sessions` — Focus tracking
- `goals` — User goals (synced with backend)
- `observations` — Screen context snapshots
- `live_notes` — AI-generated notes during recording

### Adding Custom Tables

Always prefix with `custom_` and add migrations at the end of `setupMigrations()`:

```swift
// In RewindDatabase.swift, at the end of setupMigrations():
migrator.registerMigration("addCustomDailySummaries") { db in
    try db.create(table: "custom_daily_summaries") { t in
        t.autoIncrementedPrimaryKey("id")
        t.column("date", .date).notNull()
        t.column("summary", .text).notNull()
        t.column("conversation_ids", .text) // JSON array
        t.column("created_at", .datetime).notNull()
            .defaults(sql: "CURRENT_TIMESTAMP")
    }
}
```

Model:
```swift
struct CustomDailySummary: Codable, FetchableRecord, PersistableRecord, Identifiable {
    var id: Int64?
    var date: Date
    var summary: String
    var conversationIds: String?
    var createdAt: Date

    static let databaseTableName = "custom_daily_summaries"

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }
}
```

### Querying Existing Data

Use the `execute_sql` tool to explore data before writing code:

```sql
-- Recent conversations
SELECT id, json_extract(structured, '$.title') as title, created_at
FROM transcription_sessions ORDER BY created_at DESC LIMIT 10;

-- Action items
SELECT id, description, completed, created_at FROM action_items
WHERE deleted = 0 ORDER BY created_at DESC LIMIT 20;

-- Memories
SELECT id, content, category, created_at FROM memories
ORDER BY created_at DESC LIMIT 20;
```

## Backend API Reference

The app talks to the backend via `APIClient.swift`. Key endpoints (read-only, cannot change):

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/v1/conversations` | List conversations |
| GET | `/v3/memories` | List memories |
| GET | `/v1/action-items` | List tasks |
| POST | `/v1/action-items` | Create task |
| PATCH | `/v1/action-items/{id}` | Update task |
| GET | `/v1/goals` | List goals |
| GET | `/v1/chat_sessions` | List chat sessions |

Data from these endpoints is synced into the local SQLite tables automatically. Read from SQLite, not from the API directly.

## Architecture Patterns

### SwiftUI Views
All views use SwiftUI. Common patterns in the codebase:
- `@StateObject` / `@ObservedObject` for view models
- `@AppStorage` for UserDefaults persistence
- Actor-based storage for thread-safe database access
- `OmiColors` for themed colors, `.scaledFont()` for text

### Data Flow
```
Backend API → Storage Actors → SQLite (GRDB) → SwiftUI Views
                                    ↑
                            Custom features read/write here
```

### Adding a New Feature
1. Create a new SwiftUI view in the appropriate directory
2. If it needs custom data, add a GRDB migration + model
3. If it needs existing data, query from SQLite via a Storage actor
4. Wire it into the navigation (MenuBar.swift or relevant page)

## Safety Rules

1. **Never modify sync logic** — ActionItemStorage, MemoryStorage, etc. handle bidirectional sync with the backend. Breaking this corrupts user data.
2. **Never change Firestore schemas** — The backend API defines the schema. Custom data goes in local SQLite only.
3. **Always use `custom_` prefix** for new tables — prevents conflicts with existing tables and future migrations.
4. **Test with `execute_sql` first** — Before writing Swift code that queries data, verify your SQL works.
5. **Incremental changes** — Make small changes, build, verify. Don't rewrite large sections at once.
