/**
 * Pi extension: nooto-gstack — vendor gstack skill workflows as Pi slash commands.
 *
 * Vendors skill definitions from github.com/garrytan/gstack (MIT, commit e8893a18).
 * See skills/gstack/NOTICE.md for full attribution.
 *
 * Two integration points:
 *
 * 1. **Skill discovery** — on `resources_discover`, returns the `skills/gstack/`
 *    directory so Pi includes all 9 skill descriptions in its system prompt and
 *    makes them loadable via `/skill:plan-ceo-review` etc.
 *
 * 2. **Slash commands** — registers `/plan-ceo-review`, `/plan-eng-review`,
 *    `/review`, `/ship`, `/browse`, `/qa`, `/qa-only`, `/setup-browser-cookies`,
 *    and `/retro` via `pi.registerCommand`. Each handler reads the corresponding
 *    SKILL.md at invocation time, appends any user arguments, and sends the full
 *    content as a user message so the LLM follows it immediately.
 *
 * The `/browse` command is stubbed: gstack's browse skill requires a Bun-compiled
 * binary not present in this environment. Browser automation is available via the
 * existing `playwright-bridge` MCP tool registered by nooto-mcp.
 *
 * Tolerates per-skill failures: if a SKILL.md is missing or unreadable, the
 * command reports the error via a user message without crashing the extension.
 *
 * Note: The upstream SKILL.md files contain a preamble bash block that invokes
 * `~/.claude/skills/gstack/bin/gstack-*` binaries. These don't exist in this
 * environment, but every call uses `2>/dev/null || true` fallbacks and fails
 * gracefully. The substantive skill instructions that follow are unaffected.
 */

import type { ExtensionAPI } from "@mariozechner/pi-coding-agent";
import { readFileSync } from "node:fs";
import { resolve, dirname } from "node:path";
import { fileURLToPath } from "node:url";

// ---------------------------------------------------------------------------
// Module-level constants — computed once at load time
// ---------------------------------------------------------------------------

/** Absolute path to the vendored skills/gstack/ directory. */
const SKILLS_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "../../skills/gstack");

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

/**
 * Read a skill's SKILL.md content.
 * Returns the file content on success, or an error string on failure.
 * Operates directly on the file and handles ENOENT rather than pre-checking
 * existence (avoids TOCTOU and redundant stat syscall).
 */
function readSkillContent(skillName: string): { ok: true; content: string } | { ok: false; error: string } {
  const skillFile = resolve(SKILLS_DIR, skillName, "SKILL.md");
  try {
    return { ok: true, content: readFileSync(skillFile, "utf8") };
  } catch (err) {
    const code = (err as NodeJS.ErrnoException).code;
    const msg = err instanceof Error ? err.message : String(err);
    return { ok: false, error: code === "ENOENT" ? `Skill file not found: ${skillFile}` : `Failed to read ${skillFile}: ${msg}` };
  }
}

// ---------------------------------------------------------------------------
// Command definitions
// ---------------------------------------------------------------------------

interface CommandSpec {
  /** The slash command name (no leading slash). */
  name: string;
  /** Human-readable description for Pi's command list. */
  description: string;
  /** Corresponding skill directory name under skills/gstack/. */
  skillDir: string;
  /** When true, the command is stubbed and emits stubMessage instead of skill content. */
  stubbed?: boolean;
  /** Message shown when stubbed === true. */
  stubMessage?: string;
}

const COMMANDS: CommandSpec[] = [
  {
    name: "plan-ceo-review",
    description:
      "CEO/founder-mode plan review: rethink the problem, find the 10-star product, " +
      "challenge premises, expand or reduce scope. Use when asked to 'think bigger', " +
      "'strategy review', or 'is this ambitious enough'.",
    skillDir: "plan-ceo-review",
  },
  {
    name: "plan-eng-review",
    description:
      "Eng manager-mode plan review: lock in architecture, data flow, diagrams, edge " +
      "cases, test coverage, and performance. Use when asked to 'review the architecture', " +
      "'engineering review', or 'lock in the plan'.",
    skillDir: "plan-eng-review",
  },
  {
    name: "review",
    description:
      "Pre-landing PR review: analyzes diff against the base branch for SQL safety, LLM " +
      "trust boundary violations, conditional side effects, and other structural issues. " +
      "Use when asked to 'review this PR', 'code review', or 'check my diff'.",
    skillDir: "review",
  },
  {
    name: "ship",
    description:
      "Ship workflow: detect + merge base branch, run tests, review diff, bump VERSION, " +
      "update CHANGELOG, commit, push, create PR. Use when asked to 'ship', 'deploy', " +
      "'create a PR', or 'get it deployed'.",
    skillDir: "ship",
  },
  {
    name: "browse",
    description:
      "[Stubbed] gstack's headless browse binary is not available. " +
      "Use playwright-bridge MCP tools instead (registered by nooto-mcp).",
    skillDir: "browse",
    stubbed: true,
    stubMessage:
      "The /browse command requires gstack's Bun-compiled browse binary, which is not " +
      "bundled in this environment.\n\n" +
      "Browser automation is available via the playwright-bridge MCP tools registered by " +
      "the nooto-mcp extension:\n" +
      "  - playwright-bridge__browser_navigate — navigate to a URL\n" +
      "  - playwright-bridge__browser_snapshot — get an accessibility snapshot\n" +
      "  - playwright-bridge__browser_take_screenshot — capture a screenshot\n" +
      "  - playwright-bridge__browser_click — click an element\n\n" +
      "You can still read the full browse skill with /skill:browse.",
  },
  {
    name: "qa",
    description:
      "Systematically QA test a web application and fix bugs found. Runs QA testing, then " +
      "iteratively fixes bugs, commits each fix atomically, and re-verifies. Use when asked " +
      "to 'qa', 'test this site', 'find bugs', or 'test and fix'.",
    skillDir: "qa",
  },
  {
    name: "qa-only",
    description:
      "Report-only QA testing: tests a web application and produces a structured report " +
      "with health score, screenshots, and repro steps — never fixes anything. Use when " +
      "asked to 'just report bugs', 'qa report only', or 'test but don't fix'.",
    skillDir: "qa-only",
  },
  {
    name: "setup-browser-cookies",
    description:
      "Import cookies from your real Chromium browser into the headless browse session. " +
      "Opens an interactive picker UI to select which cookie domains to import. " +
      "Use before QA testing authenticated pages.",
    skillDir: "setup-browser-cookies",
  },
  {
    name: "retro",
    description:
      "Weekly engineering retrospective: analyzes commit history, work patterns, and code " +
      "quality metrics with persistent history and trend tracking. Team-aware: breaks down " +
      "per-person contributions with praise and growth areas.",
    skillDir: "retro",
  },
];

// ---------------------------------------------------------------------------
// Extension factory
// ---------------------------------------------------------------------------

export default function registerGstack(pi: ExtensionAPI): void {
  // -------------------------------------------------------------------------
  // 1. Skill path registration via resources_discover
  // -------------------------------------------------------------------------
  // Pi scans skills/gstack/ and discovers the 9 skill directories.
  // Descriptions land in the system prompt immediately; full content loads
  // on-demand when the LLM calls read on the SKILL.md or the user runs
  // /skill:<name>. Unknown frontmatter fields (preamble-tier, version,
  // triggers, etc.) are ignored per Pi's lenient skill loader.

  pi.on("resources_discover", (_event, _ctx) => {
    return { skillPaths: [SKILLS_DIR] };
  });

  // -------------------------------------------------------------------------
  // 2. Slash command registration
  // -------------------------------------------------------------------------
  // Each command reads its SKILL.md at invocation time and sends the full
  // content as a user message. User arguments (if any) are appended after
  // a "User:" separator, matching Pi's /skill:<name> <args> convention.

  for (const spec of COMMANDS) {
    pi.registerCommand(spec.name, {
      description: spec.description,
      handler: async (args, ctx) => {
        if (spec.stubbed) {
          ctx.ui.notify(`/${spec.name}: use playwright-bridge MCP tools instead`, "warning");
          pi.sendUserMessage(spec.stubMessage ?? "This command is not available in this environment.");
          return;
        }

        const result = readSkillContent(spec.skillDir);
        if (!result.ok) {
          ctx.ui.notify(`gstack/${spec.skillDir}: ${result.error}`, "error");
          pi.sendUserMessage(
            `Failed to load skill "${spec.skillDir}": ${result.error}\n\n` +
              "Check that the skills/gstack/ directory is present in the Pi sidecar bundle.",
          );
          return;
        }

        const userArgs = (args ?? "").trim();
        const prompt = userArgs ? `${result.content}\n\nUser: ${userArgs}` : result.content;
        pi.sendUserMessage(prompt);
      },
    });
  }
}
