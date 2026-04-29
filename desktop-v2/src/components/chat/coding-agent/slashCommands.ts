/**
 * Slash commands surfaced in the prompt-input autocomplete. Mirror the
 * commands registered by the nooto-gstack Pi extension plus a few Pi
 * built-ins. When this list grows, keep it in sync with
 * `extensions/nooto-gstack/index.ts`.
 */

export interface SlashCommand {
  /** Command name without the leading slash. */
  name: string;
  /** One-line description shown in the menu. */
  description: string;
  /** Display category for grouping. */
  group: "Workflow" | "QA" | "Session" | "Pi";
}

export const SLASH_COMMANDS: SlashCommand[] = [
  // gstack — workflow
  { name: "plan-ceo-review", description: "Founder-style scope + product review on a feature plan", group: "Workflow" },
  { name: "plan-eng-review", description: "Staff Engineer architecture review", group: "Workflow" },
  { name: "review", description: "Paranoid pre-landing PR review with specialist checklists", group: "Workflow" },
  { name: "ship", description: "End-to-end ship: tests, changelog, PR", group: "Workflow" },
  { name: "retro", description: "Engineering retrospective", group: "Workflow" },

  // gstack — QA
  { name: "qa", description: "Find → fix → verify QA loop", group: "QA" },
  { name: "qa-only", description: "Read-only QA report (no fixes)", group: "QA" },
  { name: "browse", description: "Headless browser session (use playwright MCP tools)", group: "QA" },
  { name: "setup-browser-cookies", description: "Cookie import for authenticated QA flows", group: "QA" },

  // Pi built-ins
  { name: "clear", description: "Clear the current chat history", group: "Session" },
  { name: "compact", description: "Manually compact the conversation", group: "Session" },
  { name: "help", description: "Show Pi help", group: "Pi" },
];

/**
 * Pull the slash-command query from the start of an input.
 * Returns null if the input isn't a slash command (no leading `/`),
 * or once the user has typed a space (command name committed).
 */
export function parseSlashQuery(input: string): string | null {
  if (!input.startsWith("/")) return null;
  const rest = input.slice(1);
  if (rest.includes(" ") || rest.includes("\n")) return null;
  return rest;
}

export function filterCommands(query: string): SlashCommand[] {
  if (!query) return SLASH_COMMANDS;
  const q = query.toLowerCase();
  return SLASH_COMMANDS.filter(
    (c) =>
      c.name.toLowerCase().includes(q) ||
      c.description.toLowerCase().includes(q),
  );
}
