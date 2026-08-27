// Isolated config dir for Omi's built-in Claude Code coding agent.
//
// Omi's in-app "Sign in to Claude" and the ACP bridge it spawns must NEVER read
// or write the user's real `~/.claude` — that directory belongs to the user's
// own Claude Code CLI (its OAuth login in `.credentials.json`, its MCP servers
// in `.claude.json`). Sharing it meant Omi's inference-only sign-in OVERWROTE
// the user's CLI login (a feature downgrade), and Omi's "Sign out of Claude"
// deleted it — logging the user out of their personal CLI too. The macOS port
// isolates this in Keychain; on Windows we give the agent its own
// CLAUDE_CONFIG_DIR under Omi's userData.
//
// Setting CLAUDE_CONFIG_DIR relocates the WHOLE agent config surface — both
// `<dir>/.credentials.json` and the SDK's `<dir>/.claude.json` (verified against
// the bundled @anthropic-ai/claude-agent-sdk: it resolves `.claude.json` from
// `CLAUDE_CONFIG_DIR ?? homedir`). So the agent becomes fully self-contained and
// the user's real `~/.claude` / `~/.claude.json` are untouched by Omi. (The
// agent therefore does not inherit the user's real MCP servers — an accepted
// tradeoff; the separate memory-export flow that registers Omi memory in the
// user's own `~/.claude.json` is for the user's external CLI, not this agent.)
//
// Electron-free by design so it stays unit-testable: the caller passes
// `app.getPath('userData')`; nothing here imports electron.

import { mkdirSync } from 'fs'
import { join } from 'path'

/** The Omi-owned Claude agent config dir, given the app's userData dir. */
export function claudeAgentConfigDir(userDataDir: string): string {
  return join(userDataDir, 'claude-agent')
}

/**
 * Pin `process.env.CLAUDE_CONFIG_DIR` to Omi's isolated agent dir (creating it),
 * so every claudeOAuth reader/writer (which default to `process.env`) and the
 * spawned ACP bridge (which explicitly allowlists this variable) agree on the
 * isolated location instead of the user's `~/.claude`. Overrides inherited values —
 * isolation is the whole point, so Omi never defers to a user-set dir.
 *
 * Call once at startup, before the coding-agent IPC is registered or any agent
 * subprocess is spawned. Returns the resolved dir.
 */
export function initClaudeAgentConfigDir(userDataDir: string): string {
  const dir = claudeAgentConfigDir(userDataDir)
  mkdirSync(dir, { recursive: true })
  process.env.CLAUDE_CONFIG_DIR = dir
  return dir
}
