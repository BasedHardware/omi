---
name: build-fix
description: "Fix Swift and Rust build errors and rebuild. Use when the user says 'build fails', 'doesn't build', 'fix and rebuild', 'agents broke the build', or pastes compiler error output. Handles both Swift (xcrun swift build) and Rust (cargo build --release) compilation errors."
---

# Build Fix

Fix compilation errors in the OMI Desktop project (Swift + Rust) and get the build passing again. This is the most common interactive loop — build fails (often from concurrent agent changes), user pastes errors, Claude fixes them.

## Workflow

### Step 1: Identify the Error Source

Determine whether the error is from Swift or Rust based on the user's pasted output.

- **Swift errors**: Mention `.swift` files, `xcrun swift build`, SPM resolution, type checking
- **Rust errors**: Mention `.rs` files, `cargo build`, borrow checker, lifetime issues

Build commands for reference (DO NOT run these — let the user build):
- **Swift**: `xcrun swift build -c debug --package-path Desktop`
- **Rust**: `cd Backend-Rust && cargo build --release`

**NEVER** use bare `swift build` (SDK version mismatch). **NEVER** use `xcodebuild` (no .xcodeproj). This is a Swift Package Manager project.

### Step 2: Parse the Error Output

Extract from the compiler output:
- **File paths** and **line numbers**
- **Error type** (type mismatch, missing import, borrow checker, etc.)
- **The specific symbol or expression** that failed

Read the relevant file(s) at the indicated lines. If the error references a type or function defined elsewhere, find its definition to understand the expected signature.

### Step 3: Fix the Errors

Make **targeted fixes only** — do not refactor surrounding code.

#### Common Swift Errors

| Error Pattern | Typical Fix |
|---|---|
| `No such module 'X'` | Add `import X` to the file |
| `Cannot convert value of type 'A' to expected 'B'` | Check git diff — another agent likely changed a type. Match the new type. |
| `'X' was deprecated in macOS Y` | Update to the replacement API |
| `Sending 'X' risks causing data races` / `Non-sendable type` | Add `@Sendable`, `@MainActor`, or `nonisolated` as appropriate |
| `Missing argument for parameter 'X'` | Check the function signature (another agent may have added a parameter). Supply the missing argument. |
| `Value of type 'X' has no member 'Y'` | Property/method was renamed or removed. Find the current definition. |
| `Cannot find 'X' in scope` | Import missing, typo, or symbol was renamed by another agent. Search the codebase. |

#### Common Rust Errors

| Error Pattern | Typical Fix |
|---|---|
| `cannot borrow X as mutable` | Restructure borrows, clone if appropriate, or use interior mutability |
| `missing field X in initializer` | Another agent added a field to a struct. Add the missing field with a sensible default. |
| `mismatched types` | Check the function signature for recent changes |
| `unresolved import` | Add `use` or `mod` statement |
| `lifetime X does not live long enough` | Adjust lifetime annotations or restructure ownership |

### Step 4: Multi-Agent Awareness

When multiple agents are working on the codebase simultaneously:
- Errors may be from **other agents' incomplete changes** — tell the user if you suspect this
- Check `git diff` to see recent uncommitted changes for context
- If the error is in code you didn't write and the fix isn't obvious, **investigate before editing**
- Files may change between your read and write — re-read if an edit fails

### Step 5: After Fixing

**DO NOT rebuild automatically. DO NOT run `./run.sh`.** Tell the user the fixes are done and let them build/run manually.
