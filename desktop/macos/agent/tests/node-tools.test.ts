import { mkdtemp, mkdir, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import { isSafeSkillName, loadSkillInstructions } from "../src/runtime/node-tools.js";

describe("node tool helpers", () => {
  it("rejects traversal and path-like skill names", () => {
    expect(isSafeSkillName("dev-mode")).toBe(true);
    expect(isSafeSkillName("product_design.v1")).toBe(true);
    expect(isSafeSkillName("../secrets")).toBe(false);
    expect(isSafeSkillName("nested/skill")).toBe(false);
    expect(isSafeSkillName("..")).toBe(false);
    expect(isSafeSkillName("safe..looking")).toBe(false);
  });

  it("refuses symlink escapes from the configured skills root", async () => {
    const root = await mkdtemp(join(tmpdir(), "omi-agent-skills-"));
    const outside = await mkdtemp(join(tmpdir(), "omi-agent-skills-outside-"));
    const skillName = "escape";

    try {
      await mkdir(join(root, ".claude", "skills"), { recursive: true });
      await mkdir(join(outside, skillName), { recursive: true });
      await writeFile(join(outside, skillName, "SKILL.md"), "secret instructions");
      await symlink(join(outside, skillName), join(root, ".claude", "skills", skillName));

      const result = await loadSkillInstructions(skillName, root);

      expect(result).toBe(
        "Skill 'escape' is not available. Search with search_skills before loading a skill outside the compact catalog."
      );
    } finally {
      await rm(root, { recursive: true, force: true });
      await rm(outside, { recursive: true, force: true });
    }
  });
});
