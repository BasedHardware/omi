import { readFile, readdir, realpath } from "node:fs/promises";
import { homedir } from "node:os";
import { resolve } from "node:path";

export function isSafeSkillName(name: string): boolean {
  return /^[A-Za-z0-9._-]+$/.test(name) && name !== "." && name !== ".." && !name.includes("..");
}

export interface DiscoveredSkill {
  name: string;
  description: string;
  path: string;
}

function configuredSkillRoots(workspace = process.env.OMI_WORKSPACE ?? ""): string[] {
  return [
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
        const content = await readFile(path, "utf8");
        discovered.set(name, { name, description: skillDescription(content), path });
      } catch {
        // Ignore incomplete skills and paths outside an approved skill root.
      }
    }
  }
  return [...discovered.values()].sort((left, right) => left.name.localeCompare(right.name));
}

export async function searchSkills(query: string, workspace = process.env.OMI_WORKSPACE ?? ""): Promise<string> {
  const normalizedQuery = query.trim().toLocaleLowerCase();
  if (!normalizedQuery) return "Provide a keyword or short description of the user's request.";
  const tokens = normalizedQuery.split(/\s+/).filter(Boolean);
  const matches = (await discoverSkillCatalog(configuredSkillRoots(workspace)))
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

export async function loadSkillInstructions(name: string, workspace = process.env.OMI_WORKSPACE ?? ""): Promise<string> {
  const trimmedName = name.trim();
  if (!isSafeSkillName(trimmedName)) {
    return "Invalid skill name. Use a skill returned by the catalog or search_skills.";
  }

  const skill = (await discoverSkillCatalog(configuredSkillRoots(workspace))).find((candidate) => candidate.name === trimmedName);
  if (!skill) {
    return `Skill '${trimmedName}' is not available. Search with search_skills before loading a skill outside the compact catalog.`;
  }

  const content = await readFile(skill.path, "utf8");

  if (content && trimmedName === "dev-mode" && workspace) {
    return `Workspace: ${workspace}\n\n${content}`;
  }

  return content;
}
