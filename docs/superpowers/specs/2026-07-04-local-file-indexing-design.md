# Local File Indexing (Windows)

## Overview
This feature implements Local File Indexing for the Windows desktop app, maintaining strict feature parity with the macOS app's `FileIndexerService.swift`. The goal is to scan common developer and user directories to provide local context to the AI, without relying on external system indexers that may have varying behavior across machines.

## Architecture

We will use a Node.js-based recursive scanner running in the Electron Main process, storing metadata in `better-sqlite3`. This perfectly mirrors the macOS approach (which uses a Swift actor and GRDB/SQLite) and guarantees cross-platform consistency.

### 1. Database Schema
We will add an `indexed_files` table to the existing SQLite database.
- `id`: INTEGER PRIMARY KEY
- `path`: TEXT UNIQUE
- `filename`: TEXT
- `extension`: TEXT
- `size_bytes`: INTEGER
- `modified_at`: INTEGER (timestamp)

### 2. State Management (Settings)
We will store two flags in the app's standard configuration store (matching macOS `UserDefaults`):
- `hasCompletedFileIndexing` (boolean)
- `pendingFileIndexingChat` (integer - count of files indexed)

### 3. FileIndexerService (Main Process)
Location: `src/main/fileIndex/FileIndexerService.ts`

**Scan Constraints (Identical to macOS):**
- **Target Folders:** `Documents`, `Desktop`, `Downloads`, `Developer`, `Projects`, `Code`, `src`, `repos`, `Sites` (mapped to Windows equivalents via `app.getPath('home')`).
- **Max Depth:** 3.
- **Skip Folders:** `node_modules`, `.git`, `.cache`, `AppData`, `vendor`, `target`, `dist`, `build`.
- **Max File Size:** 500 MB.
- **Batch Size:** 500 DB inserts per transaction.

### 4. IPC and UI Flow
- The Renderer triggers `ipcRenderer.invoke('start-file-indexing')` when the user enables it in Onboarding/Settings.
- The Main process runs the scan and updates the DB.
- On completion, the Main process sends `fileIndexingComplete` back to the Renderer.
- The Chat UI picks up `pendingFileIndexingChat` and triggers the AI analysis prompt.

## Why this is the Optimal Decision
By keeping the scanning logic entirely within our Node.js codebase (rather than relying on the Windows Search API), we guarantee that we index the exact same specific developer directories (like `src/`, `repos/`) that macOS does, with the exact same exclusion rules (skipping `node_modules`). This ensures the feature behaves identically across both platforms without conflict.
