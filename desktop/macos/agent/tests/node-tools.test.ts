import { mkdtemp, mkdir, rm, symlink, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  SKILL_PART_CHAR_LIMIT,
  isSafeSkillName,
  loadSkillInstructions,
  splitSkillBody,
} from "../src/runtime/node-tools.js";

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

describe("splitSkillBody", () => {
  it("splits at H2 boundaries and keeps fenced headings inside their part", () => {
    const body = [
      "Intro paragraph.",
      "",
      "## First section",
      "first content",
      "## Second section",
      "```md",
      "## not a heading",
      "```",
      "still second section",
      "## Third section",
      "third content",
    ].join("\n");

    const parts = splitSkillBody(body);

    expect(parts.map((part) => part.title)).toEqual(["Overview", "First section", "Second section", "Third section"]);
    expect(parts[0].content).toBe("Intro paragraph.");
    expect(parts[2].content).toContain("## not a heading");
    expect(parts[2].content).toContain("still second section");
    expect(parts[3].content).toBe("third content");
  });
});

describe("load_skill progressive disclosure", () => {
  const uniqueName = () => `parts-skill-${Math.random().toString(36).slice(2, 10)}`;

  async function withSkill(body: string, run: (skillName: string, root: string) => Promise<void>) {
    const root = await mkdtemp(join(tmpdir(), "omi-agent-parts-"));
    const skillName = uniqueName();
    try {
      await mkdir(join(root, ".claude", "skills", skillName), { recursive: true });
      await writeFile(
        join(root, ".claude", "skills", skillName, "SKILL.md"),
        `---\nname: ${skillName}\ndescription: A test skill for parts\n---\n\n${body}`
      );
      await run(skillName, root);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  }

  it("returns metadata, a table of contents, and only the first section by default", async () => {
    await withSkill(
      ["Overview prose.", "## Usage", "usage instructions", "## Advanced", "advanced secrets"].join("\n"),
      async (skillName, root) => {
        const result = await loadSkillInstructions(skillName, root);
        expect(result).toContain(`Skill: ${skillName}`);
        expect(result).toContain("Description: A test skill for parts");
        expect(result).toContain("1. Overview (");
        expect(result).toContain("2. Usage (");
        expect(result).toContain("3. Advanced (");
        expect(result).toContain("part 1/3: Overview");
        expect(result).toContain("Overview prose.");
        expect(result).toContain("2. Usage (");
        expect(result).not.toContain("usage instructions");
        expect(result).not.toContain("advanced secrets");
      }
    );
  });

  it("fetches a requested part by 1-based number", async () => {
    await withSkill(
      ["Overview prose.", "## Usage", "usage instructions", "## Advanced", "advanced secrets"].join("\n"),
      async (skillName, root) => {
        const result = await loadSkillInstructions(skillName, root, { part: 3 });
        expect(result).toContain(`part 3/3: Advanced`);
        expect(result).toContain("advanced secrets");
        expect(result).not.toContain("usage instructions");
        expect(result).not.toContain("Overview prose.");
      }
    );
  });

  it("rejects out-of-range parts with the valid range", async () => {
    await withSkill("only intro", async (skillName, root) => {
      const result = await loadSkillInstructions(skillName, root, { part: 5 });
      expect(result).toContain(`Invalid part 5 for skill '${skillName}'`);
      expect(result).toContain("1 section(s)");
    });
  });

  it("returns the entire body only when part=\"all\" is requested", async () => {
    await withSkill(
      ["Overview prose.", "## Usage", "usage instructions", "## Advanced", "advanced secrets"].join("\n"),
      async (skillName, root) => {
        const everything = await loadSkillInstructions(skillName, root, { part: "all" });
        expect(everything).toContain("---");
        expect(everything).toContain(`name: ${skillName}`);
        expect(everything).toContain("advanced secrets");
        expect(everything).toContain("usage instructions");
      }
    );
  });

  it("caps a single oversized section with a truncation note", async () => {
    await withSkill(`## Huge\n${"x".repeat(SKILL_PART_CHAR_LIMIT + 4096)}`, async (skillName, root) => {
      const result = await loadSkillInstructions(skillName, root, { part: 1 });
      expect(result).toContain("truncated at");
      expect(result.length).toBeLessThan(SKILL_PART_CHAR_LIMIT + 600);
    });
  });
});
