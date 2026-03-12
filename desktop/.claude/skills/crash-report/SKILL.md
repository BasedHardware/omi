---
name: crash-report
description: "Parse and investigate macOS crash reports and Sentry crashes. Use when user pastes a crash report (Translated Report), says 'app crashed', 'investigate crash', or references a Sentry crash. Identifies crashing thread, maps stack frames to source code, cross-references with git history."
---

# Crash Report Investigation

## Overview

Parse macOS Translated Crash Reports or Sentry crash data for the OMI Desktop app. Identify the crashing frame, map it to source code, check recent changes, and propose a fix.

## Crash Report Format (macOS Translated Report)

```
Thread X Crashed:
0   OMI        0x... functionName + offset (file.swift:line)
1   OMI        0x... callerFunction + offset
...
```

## Investigation Workflow

### 1. Find the Crashing Thread

Look for `Thread X Crashed` or `Exception Type` in the report. The crashing thread header is always marked explicitly.

### 2. Identify the Crashing Frame

First frame in the crashing thread that belongs to OMI code (not system frameworks like `libsystem_kernel`, `AppKit`, `SwiftUI`, etc.).

### 3. Map to Source Code

Use the function name and `file.swift:line` from the frame to locate the code:

```bash
# Search by function name
grep -rn "func functionName" Desktop/Sources/
# Or read the exact file and line
```

### 4. Check Recent Changes

```bash
git log --oneline --since="1 week ago" -- <crashing-file>
```

### 5. Check Sentry for Known Issues

```bash
source .env && curl -s -H "Authorization: Bearer $SENTRY_AUTH_TOKEN" \
  "https://sentry.io/api/0/projects/$SENTRY_ORG/$SENTRY_PROJECT/issues/?query=<error-type-or-function-name>&limit=10"
```

### 6. Check Frequency

How many users are affected? Check Sentry issue event count and user count.

### 7. Check App Logs

Review `/private/tmp/omi.log` for errors just before the crash timestamp.

### 8. Propose Fix

Based on root cause analysis, propose a concrete code fix.

## Common Crash Patterns in OMI Desktop

| Pattern | Symptoms | Investigation |
|---------|----------|---------------|
| **SQLite/GRDB** | Database locked, WAL corruption, unique constraint violations | Check concurrent DB access, transaction handling |
| **Force unwrap (!)** | Nil value encountered | Check optional handling, find the `!` in source |
| **Memory pressure** | OOM kills | Video encoding buffers, screen capture allocations |
| **Thread safety** | Main thread assertion, data race | Check `@MainActor`, `DispatchQueue` usage |
| **ScreenCaptureKit** | SCStream failures, filter errors | Check `SCStreamConfiguration`, entitlements |

## Key Exception Types

| Exception | Meaning |
|-----------|---------|
| `EXC_BAD_ACCESS` | Memory corruption, use-after-free, nil dereference |
| `EXC_CRASH (SIGABRT)` | Assertion failure, force unwrap nil |
| `EXC_CRASH (SIGKILL)` | System killed process (memory pressure, watchdog) |
| `EXC_BREAKPOINT` | Swift runtime error (array out of bounds, etc.) |
