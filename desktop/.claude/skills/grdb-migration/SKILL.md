---
name: grdb-migration
description: "Add SQLite schema migrations using GRDB. Use when adding database columns, creating tables, modifying schema, or fixing migration issues. Triggers: 'add column', 'new table', 'database migration', 'schema change', 'GRDB migration'."
---

# GRDB Migration

## Overview

All SQLite schema changes in the OMI Desktop app go through GRDB's `DatabaseMigrator` in a single file. Migrations are append-only and order-dependent. This skill documents the exact steps for adding a new migration.

## Where Migrations Live

**Single file**: `Desktop/Sources/Rewind/Core/RewindDatabase.swift`

All migrations are registered inside the `private func migrate(_ queue: DatabasePool) throws` method (starts around line 799). The method creates a `DatabaseMigrator`, registers all migrations in order, then calls `try migrator.migrate(queue)` at the end.

## How to Add a Migration

### Step 1: Determine the Migration Name

Migration names are descriptive camelCase strings. Look at the last `registerMigration` call in the `migrate()` function to understand the current chain. As of now there are 50 migrations, with the last one being `"createIndexedFiles"`.

Pick a descriptive name like:
- `"addColumnNameToTableName"` for adding columns
- `"createTableName"` for new tables
- `"backfillSomeData"` for data migrations

### Step 2: Add the Migration

Add your new `migrator.registerMigration(...)` call **immediately before** the `try migrator.migrate(queue)` line at the end of the function. Never insert migrations in the middle of the chain.

#### Template: Add Column

```swift
migrator.registerMigration("addMyNewColumn") { db in
    try db.alter(table: "table_name") { t in
        t.add(column: "columnName", .text)              // nullable
        // OR with default:
        // t.add(column: "columnName", .boolean).notNull().defaults(to: false)
    }
}
```

GRDB column types: `.text`, `.integer`, `.double`, `.boolean`, `.datetime`, `.blob`

#### Template: Create Table

```swift
migrator.registerMigration("createMyTable") { db in
    try db.create(table: "my_table") { t in
        t.autoIncrementedPrimaryKey("id")
        t.column("name", .text).notNull()
        t.column("value", .integer)
        t.column("parentId", .integer)
            .references("parent_table", onDelete: .cascade)
        t.column("createdAt", .datetime).notNull()
        t.column("updatedAt", .datetime).notNull()
    }

    // Add indexes for common queries
    try db.create(index: "idx_my_table_name", on: "my_table", columns: ["name"])
}
```

#### Template: Create FTS5 Virtual Table

```swift
migrator.registerMigration("createMyTableFTS") { db in
    try db.execute(sql: """
        CREATE VIRTUAL TABLE my_table_fts USING fts5(
            searchableColumn1,
            searchableColumn2,
            content='my_table',
            content_rowid='id'
        )
    """)

    // Triggers to keep FTS in sync
    try db.execute(sql: """
        CREATE TRIGGER my_table_ai AFTER INSERT ON my_table BEGIN
            INSERT INTO my_table_fts(rowid, searchableColumn1, searchableColumn2)
            VALUES (new.id, new.searchableColumn1, new.searchableColumn2);
        END
    """)

    try db.execute(sql: """
        CREATE TRIGGER my_table_ad AFTER DELETE ON my_table BEGIN
            INSERT INTO my_table_fts(my_table_fts, rowid, searchableColumn1, searchableColumn2)
            VALUES ('delete', old.id, old.searchableColumn1, old.searchableColumn2);
        END
    """)

    try db.execute(sql: """
        CREATE TRIGGER my_table_au AFTER UPDATE ON my_table BEGIN
            INSERT INTO my_table_fts(my_table_fts, rowid, searchableColumn1, searchableColumn2)
            VALUES ('delete', old.id, old.searchableColumn1, old.searchableColumn2);
            INSERT INTO my_table_fts(rowid, searchableColumn1, searchableColumn2)
            VALUES (new.id, new.searchableColumn1, new.searchableColumn2);
        END
    """)
}
```

### Step 3: Update the Swift Model

Model files live in `Desktop/Sources/Rewind/Core/` (e.g., `RewindModels.swift`, `TranscriptionModels.swift`, `ActionItemModels.swift`, `MemoryModels.swift`, `ProactiveModels.swift`) or nearby directories (`LiveNotes/LiveNoteModels.swift`, `FileIndexing/IndexedFileRecord.swift`).

Models conform to `Codable, FetchableRecord, PersistableRecord, Identifiable`:

```swift
struct MyRecord: Codable, FetchableRecord, PersistableRecord, Identifiable {
    var id: Int64?
    var name: String
    var newColumn: String?  // <-- add your new property

    static let databaseTableName = "my_table"

    init(id: Int64? = nil, name: String, newColumn: String? = nil) {
        self.id = id
        self.name = name
        self.newColumn = newColumn
    }

    mutating func didInsert(_ inserted: InsertionSuccess) {
        id = inserted.rowID
    }
}
```

Key rules:
- The property name must match the column name exactly (GRDB uses Codable mapping)
- New columns added via `ALTER TABLE` must be optional (`?`) or have a default value, since existing rows won't have data
- Set `static let databaseTableName` to match the SQL table name
- Include `didInsert` callback for auto-increment primary keys

### Step 4: Update the Storage Actor (if needed)

Storage actors that use `RewindDatabase.shared.getDatabaseQueue()` live alongside models:
- `TranscriptionStorage.swift` for `transcription_sessions` / `transcription_segments`
- `ActionItemStorage.swift` for `action_items` / `staged_tasks`
- `MemoryStorage.swift` for `memories`
- `ProactiveStorage.swift` for `proactive_extractions` / `focus_sessions`
- `NoteStorage.swift` for `live_notes`
- `GoalStorage.swift` for `goals`

Add any new query/insert/update methods to the relevant storage actor.

## Pitfalls

1. **Never reorder or rename existing migrations.** GRDB tracks which migrations have run by name. Renaming or reordering causes them to re-run or be skipped on existing databases.

2. **ALTER TABLE limitations.** SQLite `ALTER TABLE ... ADD COLUMN` does not support `NOT NULL` without a default value. If you need a non-null column, either provide `.defaults(to: ...)` or add it as nullable and backfill in the same migration.

3. **WAL mode contention.** The database runs in WAL mode with `DatabasePool`. Migrations run inside a write transaction. Long-running data migrations (backfills) can block reads. For large backfills, consider doing them in batches outside the migration (see `reduceOCRDataPrecisionIfNeeded()` at the bottom of `RewindDatabase.swift` for an example of a background batch migration).

4. **Migration errors are fatal on launch.** If a migration throws, `initialize()` throws and the database is unusable. Test your SQL carefully. For risky data migrations, wrap in do/catch and log rather than crash.

5. **No-op migrations are fine.** If you need to "skip" a migration version (e.g., the migration was already handled differently), register an empty closure: `migrator.registerMigration("myMigration") { _ in }`

## Verification

After adding a migration:
1. Delete the local database to test fresh creation: `rm ~/Library/Application\ Support/Omi/users/*/omi.db*`
2. Run the app via `./run.sh` to verify the migration succeeds
3. Check `/private/tmp/omi.log` for "RewindDatabase: Initialized successfully"
4. To inspect the schema: `sqlite3 ~/Library/Application\ Support/Omi/users/*/omi.db ".schema table_name"`
