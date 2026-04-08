# Onboarding Figma Sync

This workflow keeps the macOS onboarding exported from code and synced into the `omi` Figma file on the `500k users` page.

## How it works

1. A user LaunchAgent watches `desktop/Desktop/Sources` and `desktop/Desktop/Resources`.
2. On a change, it copies onboarding-related source files into a clean export worktree.
3. It applies export-only preview overrides in that worktree so all onboarding steps render deterministically.
4. It exports the onboarding screens from SwiftUI code.
5. It serves a local preview page and pushes that page into Figma through the authenticated Figma MCP code-to-canvas flow.
6. It replaces the `OMI Onboarding Sync` frame on the `500k users` page.

## Install

Run:

```bash
scripts/install_onboarding_figma_sync.sh
```

Requirements:

- `codex` available in `PATH`
- `node` available in `PATH`
- authenticated Figma MCP access in Codex on that Mac
- the user has access to the `omi` Figma file

## Uninstall

Run:

```bash
scripts/uninstall_onboarding_figma_sync.sh
```

## Logs

- Main log: `~/Library/Application Support/OMIOnboardingSync/sync.log`
- Last result: `~/Library/Application Support/OMIOnboardingSync/last_result.txt`
- LaunchAgent stdout: `~/Library/Application Support/OMIOnboardingSync/launchd.out.log`
- LaunchAgent stderr: `~/Library/Application Support/OMIOnboardingSync/launchd.err.log`
