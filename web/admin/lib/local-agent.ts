/**
 * The local coding-agent endpoint (`POST /api/omi/agent/customize`) spawns
 * claude/codex with permission-bypass flags, so it exists only on a
 * developer's machine: never when NODE_ENV is production, and never without
 * the explicit ADMIN_LOCAL_AGENT=1 opt-in. The dashboard asks `GET` on the
 * same route and hides the widget while the server reports it disabled.
 */

/** Local development only: not production, and the explicit opt-in set. */
export function localAgentEnabled(
  env: NodeJS.ProcessEnv = process.env
): boolean {
  return env.NODE_ENV !== "production" && env.ADMIN_LOCAL_AGENT === "1";
}

const ENV_EXACT = new Set(["PATH", "HOME", "USER", "SHELL", "TMPDIR", "LANG"]);
const ENV_PREFIXES = ["ANTHROPIC_", "OPENAI_", "CLAUDE_", "CODEX_"];

/**
 * The child process environment: PATH/HOME so the CLI is found and runs,
 * plus only the CLI's own auth variables. Never `process.env` — the admin
 * server process holds Firebase credentials, cron secrets and tokens the
 * spawned agent must not inherit.
 */
export function localAgentSpawnEnv(
  env: NodeJS.ProcessEnv = process.env
): NodeJS.ProcessEnv {
  const minimal: Record<string, string> = {};
  for (const [key, value] of Object.entries(env)) {
    if (value === undefined) continue;
    if (ENV_EXACT.has(key) || ENV_PREFIXES.some((p) => key.startsWith(p))) {
      minimal[key] = value;
    }
  }
  return minimal as NodeJS.ProcessEnv;
}
