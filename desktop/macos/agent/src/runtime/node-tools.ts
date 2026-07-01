import { readFile, realpath } from "node:fs/promises";
import { homedir } from "node:os";
import { resolve } from "node:path";

export function isSafeSkillName(name: string): boolean {
  return /^[A-Za-z0-9._-]+$/.test(name) && name !== "." && name !== ".." && !name.includes("..");
}

export async function loadSkillInstructions(name: string, workspace = process.env.OMI_WORKSPACE ?? ""): Promise<string> {
  const trimmedName = name.trim();
  if (!isSafeSkillName(trimmedName)) {
    return "Invalid skill name. Use the exact skill name listed in available_skills.";
  }

  const roots = [
    workspace ? resolve(workspace, ".claude", "skills") : "",
    resolve(homedir(), ".claude", "skills"),
  ].filter(Boolean);

  let content: string | null = null;
  for (const root of roots) {
    let realRoot: string;
    let realFilePath: string;
    try {
      realRoot = await realpath(root);
      realFilePath = await realpath(resolve(root, trimmedName, "SKILL.md"));
    } catch {
      continue;
    }
    if (!realFilePath.startsWith(`${realRoot}/`)) {
      continue;
    }
    try {
      content = await readFile(realFilePath, "utf8");
      break;
    } catch {
      // Try the next configured skill location.
    }
  }

  if (content && trimmedName === "dev-mode" && workspace) {
    return `Workspace: ${workspace}\n\n${content}`;
  }

  return content ?? `Skill '${trimmedName}' not found. Check the name matches one listed in <available_skills>.`;
}
