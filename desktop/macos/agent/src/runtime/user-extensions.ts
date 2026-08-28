import { existsSync, readFileSync } from "fs";
import { join } from "path";

/**
 * User-managed agent extensions under ~/.omi, written by the desktop app and
 * hand-editable: mcp.json (standard client format) and the skills plugin dir.
 *
 * Both are read per session so newly added servers, refreshed tokens, and new
 * skills apply without restarting the runtime. Every failure is fail-open: a
 * missing or malformed file means "no user extensions", never a broken chat.
 */

export type UserHttpMcpServer = {
  name: string;
  type: "http" | "sse";
  url: string;
  headers?: Array<{ name: string; value: string }>;
};

const NAME_RE = /^[a-zA-Z0-9_-]{1,64}$/;


/**
 * Claude Code options for loading the user-skills plugin, or null when the
 * directory is absent or not a valid plugin (no .claude-plugin/plugin.json).
 * Passing an invalid path to the SDK would fail the session, so we gate here.
 */
export function userSkillsPluginOptions(
  pluginDir: string | undefined,
): { plugins: Array<{ type: "local"; path: string }> } | null {
  if (!pluginDir || !existsSync(join(pluginDir, ".claude-plugin", "plugin.json"))) {
    return null;
  }
  return { plugins: [{ type: "local", path: pluginDir }] };
}

export type UserStdioMcpServer = {
  name: string;
  command: string;
  args: string[];
  env?: Array<{ name: string; value: string }>;
};

export type UserMcpServer = UserHttpMcpServer | UserStdioMcpServer;

export function isStdioServer(server: UserMcpServer): server is UserStdioMcpServer {
  return typeof (server as UserStdioMcpServer).command === "string";
}

/**
 * `~/.omi/mcp.json` in the standard client format used by Claude Desktop and
 * friends: {"mcpServers": {"<name>": {"command", "args", "env"} | {"url",
 * "headers"|"token"}}}. Hand-editable; the desktop app also writes it.
 */
export function loadLocalMcpConfig(
  filePath: string | undefined,
  reservedNames: ReadonlySet<string>,
  logErr?: (msg: string) => void,
): UserMcpServer[] {
  if (!filePath || !existsSync(filePath)) return [];
  let parsed: unknown;
  try {
    parsed = JSON.parse(readFileSync(filePath, "utf8"));
  } catch (err) {
    logErr?.(`local-mcp: unreadable config at ${filePath}: ${String(err)}`);
    return [];
  }
  const entries = (parsed as { mcpServers?: unknown })?.mcpServers;
  if (!entries || typeof entries !== "object" || Array.isArray(entries)) return [];

  const servers: UserMcpServer[] = [];
  const seen = new Set(reservedNames);
  for (const [name, raw] of Object.entries(entries as Record<string, unknown>)) {
    if (!NAME_RE.test(name) || seen.has(name)) {
      logErr?.(`local-mcp: skipping server with invalid or duplicate name: ${name}`);
      continue;
    }
    if (!raw || typeof raw !== "object") continue;
    const entry = raw as Record<string, unknown>;

    if (typeof entry.command === "string" && entry.command.trim()) {
      const args = Array.isArray(entry.args)
        ? entry.args.filter((a): a is string => typeof a === "string")
        : [];
      const envObject =
        entry.env && typeof entry.env === "object" && !Array.isArray(entry.env)
          ? (entry.env as Record<string, unknown>)
          : {};
      const env = Object.entries(envObject)
        .filter((pair): pair is [string, string] => typeof pair[1] === "string")
        .map(([envName, value]) => ({ name: envName, value }));
      seen.add(name);
      servers.push({ name, command: entry.command.trim(), args, ...(env.length ? { env } : {}) });
      continue;
    }

    if (typeof entry.url === "string" && /^https?:\/\//.test(entry.url)) {
      const headersObject =
        entry.headers && typeof entry.headers === "object" && !Array.isArray(entry.headers)
          ? (entry.headers as Record<string, unknown>)
          : {};
      const headers = Object.entries(headersObject)
        .filter((pair): pair is [string, string] => typeof pair[1] === "string")
        .map(([headerName, value]) => ({ name: headerName, value }));
      const auth =
        entry.auth && typeof entry.auth === "object" && !Array.isArray(entry.auth)
          ? (entry.auth as Record<string, unknown>)
          : undefined;
      const bearer =
        typeof entry.token === "string" && entry.token
          ? entry.token
          : typeof auth?.access_token === "string" && auth.access_token
            ? (auth.access_token as string)
            : undefined;
      if (bearer && !headers.some((h) => h.name === "Authorization")) {
        headers.push({ name: "Authorization", value: `Bearer ${bearer}` });
      }
      seen.add(name);
      servers.push({
        name,
        type: entry.transport === "sse" ? "sse" : "http",
        url: entry.url,
        ...(headers.length ? { headers } : {}),
      });
      continue;
    }

    logErr?.(`local-mcp: skipping server ${name}: needs a command or an http(s) url`);
  }
  return servers;
}
