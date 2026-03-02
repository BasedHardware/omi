---
name: swift-warnings
description: "Triage and fix Swift compiler warnings safely. Use when user says 'warnings', 'investigate warnings', 'fix warnings', 'bunch of warnings', or pastes Swift compiler warning output. Categorizes warnings by risk and fixes only safe ones."
---

# Swift Warnings

Triage and safely fix Swift compiler warnings for the OMI Desktop project. Categorize by risk, fix safe ones, and ask before touching anything risky.

## Warning Categories

### SAFE to fix (low risk)
- **Deprecated API usage** with a clear replacement (e.g., `pluginWorkDirectory` -> `pluginWorkDirectoryURL`)
- **Unused variables** — prefix with `_`
- **Unused imports** — remove them
- **String interpolation warnings** — use explicit conversion
- **Redundant conformances** — remove the redundant protocol

### MODERATE risk (fix with caution)
- **Concurrency warnings** (`@Sendable`, `@MainActor`, `nonisolated`)
- **Protocol conformance deprecations**
- **Implicit self capture warnings**

### HIGH risk (investigate first, ask before fixing)
- **Actor isolation warnings** — may change runtime behavior
- **Sendable conformance on complex types**
- **Concurrency warnings requiring architectural changes**
- **Warnings about synchronous calls from async contexts**

## Process

1. **Collect warnings**: Build with `xcrun swift build -c debug --package-path Desktop` or use the output the user pastes.
2. **Filter out noise**: Ignore warnings from third-party dependencies (`.build/` paths, package dependencies). Focus on the project's own source files.
3. **Categorize** each warning into SAFE / MODERATE / HIGH using the categories above.
4. **Present the triage** to the user as a summary table or grouped list.
5. **Fix SAFE warnings** immediately (unless user says otherwise).
6. **For MODERATE**: explain the fix and its potential impact before editing. Fix if user approves.
7. **For HIGH**: investigate the warning, present options and tradeoffs, and do NOT edit without explicit approval.

## Key Rules

- **NEVER** "fix" a warning by suppressing it or adding `@available` unless that is genuinely the correct fix.
- **NEVER** change functionality to silence a warning.
- **When in doubt**, leave the warning alone and explain why.
- **Build command**: `xcrun swift build -c debug --package-path Desktop`
- **Focus on the user's code**, not third-party dependency warnings.
- **Do NOT run the build** after making fixes — let the user test manually.
