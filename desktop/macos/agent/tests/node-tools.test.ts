import { mkdtemp, mkdir, rm, symlink, utimes, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";
import {
  SKILL_FILE_CHAR_LIMIT,
  SKILL_PART_CHAR_LIMIT,
  configuredDisabledSkills,
  discoverSkillCatalog,
  isSafeSkillName,
  loadSkillInstructions,
  searchSkills,
  splitSkillBody,
  __resetSkillCatalogCacheForTest,
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

  it("advertises numeric part loads only in the table of contents", async () => {
    // The load_skill part parameter is number-only in the tool schema; a
    // ToC hint suggesting part: "all" costs a validation-error turn.
    await withSkill(
      ["Overview prose.", "## Usage", "usage instructions"].join("\n"),
      async (skillName, root) => {
        const result = await loadSkillInstructions(skillName, root);
        expect(result).toContain(`load a section with load_skill(name: "${skillName}", part: <n>)`);
        expect(result).not.toContain("part: \"all\"");
        expect(result).not.toContain("reads everything");
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

  it("parses a BOM-prefixed skill file's frontmatter and parts correctly", async () => {
    // Editors write a UTF-8 BOM routinely; `^---` matching must see past it.
    const root = await mkdtemp(join(tmpdir(), "omi-agent-bom-"));
    const skillName = `bom-skill-${Math.random().toString(36).slice(2, 10)}`;
    try {
      await mkdir(join(root, ".claude", "skills", skillName), { recursive: true });
      await writeFile(
        join(root, ".claude", "skills", skillName, "SKILL.md"),
        `\uFEFF---\nname: ${skillName}\ndescription: BOM prefixed skill\n---\n\nIntro prose.\n## Usage\nusage steps`
      );

      const result = await loadSkillInstructions(skillName, root);
      expect(result).toContain(`Skill: ${skillName}`);
      expect(result).toContain("Description: BOM prefixed skill");
      expect(result).toContain("1. Overview (");
      expect(result).toContain("2. Usage (");
      expect(result).toContain("part 1/2: Overview");
      expect(result).toContain("Intro prose.");
      // The frontmatter must not leak into part 1.
      expect(result).not.toMatch(/^---/m);
      expect(result).not.toContain("description: BOM prefixed skill");

      const usage = await loadSkillInstructions(skillName, root, { part: 2 });
      expect(usage).toContain("part 2/2: Usage");
      expect(usage).toContain("usage steps");

      // Discovery derives the description from the (de-BOMed) frontmatter too.
      const search = await searchSkills("BOM prefixed", root, new Set());
      expect(search).toContain(skillName);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  it("caps a single oversized section with a truncation note", async () => {
    await withSkill(`## Huge\n${"x".repeat(SKILL_PART_CHAR_LIMIT + 4096)}`, async (skillName, root) => {
      const result = await loadSkillInstructions(skillName, root, { part: 1 });
      expect(result).toContain("truncated at");
      expect(result.length).toBeLessThan(SKILL_PART_CHAR_LIMIT + 600);
    });
  });

  it("caps a sectionless (no-H2) skill on the default call and serves it as a single part", async () => {
    // No H2 headings: splitSkillBody yields exactly one "Overview" part, so the
    // default view and part 1 must both return the same capped content.
    await withSkill("x".repeat(SKILL_PART_CHAR_LIMIT + 4096), async (skillName, root) => {
      const result = await loadSkillInstructions(skillName, root);
      expect(result).toContain("truncated at");
      expect(result).toContain("part 1/1: Overview");
      expect(result.length).toBeLessThan(SKILL_PART_CHAR_LIMIT + 600);

      const part1 = await loadSkillInstructions(skillName, root, { part: 1 });
      expect(part1).toContain(`[${skillName} — part 1/1: Overview]`);
      expect(part1).toContain("truncated at");
      expect(part1.length).toBeLessThan(SKILL_PART_CHAR_LIMIT + 600);
    });
  });

  it("caps a skill whose body yields zero parts instead of returning the file uncapped", async () => {
    // A body made only of H2 headings flushes no content, so splitSkillBody
    // returns zero parts; the no-parts fallback must still cap its output.
    await withSkill("## filler\n".repeat(4096), async (skillName, root) => {
      const result = await loadSkillInstructions(skillName, root);
      expect(result).toContain("truncated at");
      expect(result.length).toBeLessThan(SKILL_PART_CHAR_LIMIT + 600);
    });
  });

  it("caps a hand-dropped skill file larger than the 128KB store limit, even for part=all", async () => {
    await withSkill("y".repeat(SKILL_FILE_CHAR_LIMIT + 4096), async (skillName, root) => {
      const everything = await loadSkillInstructions(skillName, root, { part: "all" });
      expect(everything).toContain("exceeds the 128KB skill size limit");
      expect(everything.length).toBeLessThan(SKILL_FILE_CHAR_LIMIT + 600);

      const result = await loadSkillInstructions(skillName, root);
      expect(result).toContain("truncated at");
      expect(result.length).toBeLessThan(SKILL_PART_CHAR_LIMIT + 600);
    });
  });
});

describe("skill catalog cache", () => {
  it("serves the cached description without re-reading while mtime/size hold, and re-reads after an edit", async () => {
    const root = await mkdtemp(join(tmpdir(), "omi-agent-cache-"));
    const skillName = `cache-skill-${Math.random().toString(36).slice(2, 10)}`;
    try {
      await mkdir(join(root, ".claude", "skills", skillName), { recursive: true });
      const skillPath = join(root, ".claude", "skills", skillName, "SKILL.md");
      // The two marker variants are the same byte length, so only mtime can
      // tell an edit apart.
      const marker = (word: string) =>
        `---\nname: ${skillName}\ndescription: cache-probe-${word}xx\n---\n\nbody`;
      await writeFile(skillPath, marker("aaaa"));
      const t0 = new Date();
      await utimes(skillPath, t0, t0);
      const roots = [join(root, ".claude", "skills")];

      const first = await discoverSkillCatalog(roots);
      expect(first.find((skill) => skill.name === skillName)?.description).toBe("cache-probe-aaaaxx");

      // Same size, mtime restored: a full rewrite of the content is invisible
      // to the cache — proving discovery did not re-read the file.
      await writeFile(skillPath, marker("bbbb"));
      await utimes(skillPath, t0, t0);
      const second = await discoverSkillCatalog(roots);
      expect(second.find((skill) => skill.name === skillName)?.description).toBe("cache-probe-aaaaxx");

      // An mtime bump invalidates: the edit shows up on the next discovery.
      const t1 = new Date(Date.now() + 2000);
      await utimes(skillPath, t1, t1);
      const third = await discoverSkillCatalog(roots);
      expect(third.find((skill) => skill.name === skillName)?.description).toBe("cache-probe-bbbbxx");
    } finally {
      await rm(root, { recursive: true, force: true });
      __resetSkillCatalogCacheForTest();
    }
  });
});

describe("disabled skill enforcement", () => {
  it("parses the OMI_DISABLED_SKILLS JSON export tolerantly", () => {
    expect(configuredDisabledSkills("")).toEqual(new Set());
    expect(configuredDisabledSkills("not json")).toEqual(new Set());
    expect(configuredDisabledSkills("{}")).toEqual(new Set());
    expect(configuredDisabledSkills('["a", " b ", 3, null]')).toEqual(new Set(["a", "b"]));
  });

  it("refuses a disabled skill with a clear error", async () => {
    const root = await mkdtemp(join(tmpdir(), "omi-agent-disabled-"));
    const skillName = `disabled-skill-${Math.random().toString(36).slice(2, 10)}`;
    try {
      await mkdir(join(root, ".claude", "skills", skillName), { recursive: true });
      await writeFile(
        join(root, ".claude", "skills", skillName, "SKILL.md"),
        `---\nname: ${skillName}\ndescription: Disabled on purpose\n---\n\nsecret body`
      );

      const result = await loadSkillInstructions(skillName, root, { disabledSkills: new Set([skillName]) });
      expect(result).toBe(
        `Skill '${skillName}' is disabled. Enable it in the desktop skill settings if the request needs it.`
      );
      // Enabling the skill makes it loadable again.
      const enabled = await loadSkillInstructions(skillName, root, { disabledSkills: new Set() });
      expect(enabled).toContain("secret body");
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });

  it("excludes disabled skills from search results", async () => {
    const root = await mkdtemp(join(tmpdir(), "omi-agent-disabled-search-"));
    const kept = `kept-skill-${Math.random().toString(36).slice(2, 10)}`;
    const hidden = `hidden-skill-${Math.random().toString(36).slice(2, 10)}`;
    try {
      for (const skillName of [kept, hidden]) {
        await mkdir(join(root, ".claude", "skills", skillName), { recursive: true });
        await writeFile(
          join(root, ".claude", "skills", skillName, "SKILL.md"),
          `---\nname: ${skillName}\ndescription: unique-needle-${skillName}\n---\n\nbody`
        );
      }

      const result = await searchSkills(`unique-needle-${hidden}`, root, new Set([hidden]));
      expect(result).toBe("No matching skills are available for this request.");

      const both = await searchSkills("unique-needle", root, new Set([hidden]));
      expect(both).toContain(kept);
      expect(both).not.toContain(hidden);
    } finally {
      await rm(root, { recursive: true, force: true });
    }
  });
});
