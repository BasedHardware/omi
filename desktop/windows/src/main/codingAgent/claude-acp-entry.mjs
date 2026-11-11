#!/usr/bin/env node
/**
 * Entry point for the bundled Claude Code ACP bridge
 * (@agentclientprotocol/claude-agent-acp). Spawned as a separate Node process
 * (ELECTRON_RUN_AS_NODE) by the Claude Code adapter.
 *
 * Uses only the package's public exports; cost/usage reaches the adapter via
 * the bridge's standard `usage_update` session notifications, so no patching
 * of package internals is needed (unlike the older macOS entry, which wrapped
 * newSession/prompt on a pre-rename version of this package).
 */

// Redirect console to stderr (ACP requires stdout to be pure JSON-RPC).
console.log = console.error
console.info = console.error
console.warn = console.error
console.debug = console.error

// Dynamic import AFTER the redirect: a static import would be hoisted and
// evaluated first, letting the bridge's module-load logging pollute stdout.
const { runAcp } = await import('@agentclientprotocol/claude-agent-acp')

runAcp()

// Keep process alive
process.stdin.resume()
