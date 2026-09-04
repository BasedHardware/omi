import { readFile, readdir, realpath } from "node:fs/promises";
import { homedir } from "node:os";
import { resolve } from "node:path";

export function isSafeSkillName(name: string): boolean {
  return /^[A-Za-z0-9._-]+$/.test(name) && name !== "." && name !== ".." && !name.includes("..");
}

/**
 * Strip a leading UTF-8 BOM. Editors write one routinely, and every skill
 * parser anchors on `^---` — a BOM-prefixed file silently lost its frontmatter
 * and leaked it into part 1.
 */
function stripUtf8Bom(text: string): string {
  return text.startsWith("\uFEFF") ? text.slice(1) : text;
}

export interface DiscoveredSkill {
  name: string;
  description: string;
  path: string;
}

function configuredSkillRoots(workspace = process.env.OMI_WORKSPACE ?? ""): string[] {
  // OMI_USER_SKILLS_DIR is the desktop-managed plugin of skills the user
  // created in the Apps page; its skills/ subdir follows the same layout.
  const userSkillsDir = process.env.OMI_USER_SKILLS_DIR ?? "";
  return [
    userSkillsDir ? resolve(userSkillsDir, "skills") : "",
    workspace ? resolve(workspace, ".claude", "skills") : "",
    resolve(homedir(), ".claude", "skills"),
  ].filter(Boolean);
}

function skillDescription(content: string): string {
  const frontmatter = content.match(/^---\s*\n([\s\S]*?)\n---/);
  const description = frontmatter?.[1].match(/^\s*description:\s*["']?(.+?)["']?\s*$/m)?.[1];
  const firstBodyLine = content
    .replace(/^---[\s\S]*?---\s*/, "")
    .split(/\r?\n/)
    .find((line) => line.trim().length > 0);
  return (description ?? firstBodyLine ?? "").replace(/\s+/g, " ").trim();
}

/**
 * Skill names the user disabled in the desktop app, exported to the runtime as
 * OMI_DISABLED_SKILLS (a JSON string array). Enforcement mirrors the Swift
 * compact catalog: a disabled skill never matches a search and is refused by
 * load, so the toggle is a real switch rather than advice.
 */
export function configuredDisabledSkills(raw = process.env.OMI_DISABLED_SKILLS ?? ""): Set<string> {
  if (!raw.trim()) return new Set();
  try {
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(
      parsed
        .filter((entry): entry is string => typeof entry === "string" && entry.trim().length > 0)
        .map((entry) => entry.trim())
    );
  } catch {
    return new Set();
  }
}

export async function discoverSkillCatalog(roots: readonly string[]): Promise<DiscoveredSkill[]> {
  const discovered = new Map<string, DiscoveredSkill>();
  for (const root of roots) {
    let realRoot: string;
    try {
      realRoot = await realpath(root);
    } catch {
      continue;
    }

    let entries: string[];
    try {
      entries = (await readdir(realRoot)).sort();
    } catch {
      continue;
    }
    for (const name of entries) {
      if (!isSafeSkillName(name) || discovered.has(name)) continue;
      try {
        const path = await realpath(resolve(realRoot, name, "SKILL.md"));
        if (!path.startsWith(`${realRoot}/`)) continue;
        const content = stripUtf8Bom(await readFile(path, "utf8"));
        discovered.set(name, { name, description: skillDescription(content), path });
      } catch {
        // Ignore incomplete skills and paths outside an approved skill root.
      }
    }
  }
  return [...discovered.values()].sort((left, right) => left.name.localeCompare(right.name));
}

export async function searchSkills(
  query: string,
  workspace = process.env.OMI_WORKSPACE ?? "",
  disabledSkills: ReadonlySet<string> = configuredDisabledSkills()
): Promise<string> {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  if (!normalizedQuery) return "Provide a keyword or short description of the user's request.";
  const tokens = normalizedQuery.split(/\s+/).filter(Boolean);
  const matches = (await discoverSkillCatalog(configuredSkillRoots(workspace)))
    .filter((skill) => !disabledSkills.has(skill.name))
    .map((skill) => {
      const name = skill.name.toLocaleLowerCase();
      const description = skill.description.toLocaleLowerCase();
      const score = tokens.reduce((total, token) => {
        if (name === token) return total + 8;
        if (name.includes(token)) return total + 4;
        if (description.includes(token)) return total + 1;
        return total;
      }, 0);
      return { skill, score };
    })
    .filter((candidate) => candidate.score > 0)
    .sort((left, right) => right.score - left.score || left.skill.name.localeCompare(right.skill.name))
    .slice(0, 12)
    .map(({ skill }) => `- ${skill.name}${skill.description ? `: ${skill.description}` : ""}`);
  return matches.length > 0
    ? `Matching skills:\n${matches.join("\n")}`
    : "No matching skills are available for this request.";
}

/** A skill body split at markdown H2 (##) boundaries for progressive disclosure. */
export interface SkillPart {
  title: string;
  content: string;
}

/** Cap for any single returned part, so one huge H2 section cannot flood the context. */
export const SKILL_PART_CHAR_LIMIT = 16 * 1024;

/**
 * Sanity cap on a whole skill file the runtime will serve, mirroring the 128KB
 * `maxSkillBytes` the desktop skill store enforces on skills it saves itself.
 * Hand-dropped skill folders never pass through that check, so the runtime
 * enforces the same bound here instead of assuming the file was vetted.
 */
export const SKILL_FILE_CHAR_LIMIT = 128 * 1024;

/**
 * Split a skill body at markdown H2 (##) boundaries. Content before the first H2 becomes
 * the "Overview" part. Fenced code blocks (``` or ~~~) are never split, even when a
 * fenced line looks like a heading. Empty parts are dropped.
 */
export function splitSkillBody(body: string): SkillPart[] {
  const parts: SkillPart[] = [];
  let currentLines: string[] = [];
  let currentTitle = "Overview";
  let inFence = false;
  const flush = () => {
    const content = currentLines.join("\n").trim();
    currentLines = [];
    if (content) parts.push({ title: currentTitle, content });
  };
  for (const line of body.split(/\r?\n/)) {
    if (/^\s*(```|~~~)/.test(line)) inFence = !inFence;
    const heading = inFence ? null : line.match(/^##\s+(.+?)\s*$/);
    if (heading) {
      flush();
      currentTitle = heading[1];
    } else {
      currentLines.push(line);
    }
  }
  flush();
  return parts;
}

function splitSkillFrontmatter(content: string): { meta: Record<string, string>; body: string } {
  const match = content.match(/^---\s*\n([\s\S]*?)\n---(?:\r?\n|$)/);
  if (!match) return { meta: {}, body: content };
  const meta: Record<string, string> = {};
  for (const line of match[1].split(/\r?\n/)) {
    const entry = line.match(/^([A-Za-z0-9_-]+):\s*(.*)$/);
    if (entry) meta[entry[1]] = entry[2].trim().replace(/^["']|["']$/g, "");
  }
  return { meta, body: content.slice(match[0].length) };
}

function approximateSize(content: string): string {
  const kb = content.length / 1024;
  return kb >= 1 ? `~${kb.toFixed(1)} KB` : `~${content.length} chars`;
}

function capPartContent(part: SkillPart): string {
  if (part.content.length <= SKILL_PART_CHAR_LIMIT) return part.content;
  return (
    `${part.content.slice(0, SKILL_PART_CHAR_LIMIT)}` +
    `\n\n[Section '${part.title}' truncated at ${SKILL_PART_CHAR_LIMIT} of ${part.content.length} characters; this section has no smaller subdivisions to page through.]`
  );
}

/** Cap an oversized skill file at read time with a note, so no load path can
 *  return more than the store's size bound even for a hand-dropped skill. */
function capSkillFile(content: string, name: string): string {
  if (content.length <= SKILL_FILE_CHAR_LIMIT) return content;
  return (
    `${content.slice(0, SKILL_FILE_CHAR_LIMIT)}` +
    `\n\n[Skill '${name}' truncated at ${SKILL_FILE_CHAR_LIMIT} of ${content.length} characters — the file exceeds the ${SKILL_FILE_CHAR_LIMIT / 1024}KB skill size limit.]`
  );
}

export interface LoadSkillOptions {
  /** 1-based body section to read, or "all" to opt into the full body. */
  part?: number | "all";
  /** Skill names disabled by the user; defaults to OMI_DISABLED_SKILLS. */
  disabledSkills?: ReadonlySet<string>;
}

/**
 * Progressive disclosure by default: metadata, a table of contents of the body's H2
 * sections, and only the first section's content. `options.part` fetches one section
 * (1-based) or "all" returns the entire file for callers that explicitly need it.
 * Disabled skills are refused so the desktop toggle is enforced, not advisory.
 */
export async function loadSkillInstructions(
  name: string,
  workspace = process.env.OMI_WORKSPACE ?? "",
  options: LoadSkillOptions = {}
): Promise<string> {
  const trimmedName = name.trim();
  if (!isSafeSkillName(trimmedName)) {
    return "Invalid skill name. Use a skill returned by the catalog or search_skills.";
  }

  const disabled = options.disabledSkills ?? configuredDisabledSkills();
  const skill = (await discoverSkillCatalog(configuredSkillRoots(workspace))).find((candidate) => candidate.name === trimmedName);
  if (!skill) {
    return `Skill '${trimmedName}' is not available. Search with search_skills before loading a skill outside the compact catalog.`;
  }
  if (disabled.has(trimmedName)) {
    return `Skill '${trimmedName}' is disabled. Enable it in the desktop skill settings if the request needs it.`;
  }

  const rawContent = capSkillFile(stripUtf8Bom(await readFile(skill.path, "utf8")), trimmedName);
  // The dev-mode skill intentionally carries the workspace binding above its full body.
  const workspacePrefix = rawContent && trimmedName === "dev-mode" && workspace ? `Workspace: ${workspace}\n\n` : "";

  const { meta, body } = splitSkillFrontmatter(rawContent);
  const parts = splitSkillBody(body);

  if (options.part === "all") {
    return `${workspacePrefix}${rawContent}`;
  }

  if (typeof options.part === "number") {
    const requested = Math.trunc(options.part);
    if (!Number.isFinite(requested) || requested < 1 || requested > parts.length) {
      return `Invalid part ${options.part} for skill '${trimmedName}'. It has ${parts.length} section(s); pass a part between 1 and ${parts.length}, or omit part for the overview.`;
    }
    const part = parts[requested - 1];
    return `${workspacePrefix}[${trimmedName} — part ${requested}/${parts.length}: ${part.title}]\n${capPartContent(part)}`;
  }

  if (parts.length === 0) {
    // A body with no H2 sections (or none with content) is served as a single
    // capped block: the default view must never return uncapped content —
    // only an explicit part: "all" can.
    return `${workspacePrefix}${capPartContent({ title: trimmedName, content: rawContent })}`.trimEnd();
  }

  const tableOfContents = parts
    .map((part, index) => `${index + 1}. ${part.title} (${approximateSize(part.content)})`)
    .join("\n");
  const descriptionLine = meta.description ?? skill.description;
  return [
    `Skill: ${trimmedName}`,
    descriptionLine ? `Description: ${descriptionLine}` : null,
    "",
    // Number-only instruction: the advertised part parameter is a number, and
    // telling the model to pass "all" only buys a validation-error turn.
    `Body sections (${parts.length}); load a section with load_skill(name: "${trimmedName}", part: <n>):`,
    tableOfContents,
    "",
    `${workspacePrefix}[${trimmedName} — part 1/${parts.length}: ${parts[0].title}]`,
    capPartContent(parts[0]),
  ]
    .filter((line) => line !== null)
    .join("\n");
}
