import { mkdirSync, mkdtempSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { pathToFileURL } from "node:url";
import { describe, expect, it } from "vitest";

import { defaultArtifactRoot, OmiArtifactStorage } from "../src/runtime/artifact-storage.js";

describe("OmiArtifactStorage", () => {
  it("imports emitted file artifacts into the managed artifact root", () => {
    const temp = mkdtempSync(join(tmpdir(), "omi-artifacts-"));
    const source = join(temp, "source.txt");
    const root = join(temp, "Artifacts");
    writeFileSync(source, "hello");

    const storage = new OmiArtifactStorage({ rootDir: root });
    const normalized = storage.normalizeArtifact(
      {
        kind: "file",
        role: "result",
        uri: pathToFileURL(source).toString(),
        displayName: "answer.txt",
      },
      {
        ownerId: "owner-1",
        sessionId: "session-1",
        runId: "run-1",
        attemptId: "attempt-1",
      }
    );

    expect(normalized.uri).toMatch(/^file:\/\//);
    expect(normalized.uri).not.toBe(pathToFileURL(source).toString());
    expect(normalized.uri).toContain("/Artifacts/owner-1/");
    expect(normalized.uri).toContain("/session-1/");
    expect(normalized.uri).toContain("/run-1/attempt-1/answer.txt");
    expect(normalized.metadata).toMatchObject({
      omiManaged: true,
      originalUri: pathToFileURL(source).toString(),
    });
    expect(normalized.contentHash).toMatch(/^sha256:/);
    expect(readFileSync(new URL(normalized.uri), "utf8")).toBe("hello");
    const manifest = join(new URL(normalized.uri).pathname, "..", "manifest.json");
    expect(readFileSync(manifest, "utf8")).toContain("originalUri");
  });

  it("discovers files and directories from the isolated run artifact directory", () => {
    const temp = mkdtempSync(join(tmpdir(), "omi-artifacts-"));
    const root = join(temp, "Artifacts");
    const storage = new OmiArtifactStorage({ rootDir: root });
    const scope = {
      ownerId: "owner-1",
      sessionId: "session-1",
      runId: "run-1",
      attemptId: "attempt-1",
    };
    const directory = storage.prepareRunDirectory(scope);
    writeFileSync(join(directory, "answer.md"), "# hi");
    mkdirSync(join(directory, "site"));
    writeFileSync(join(directory, "site", "index.html"), "<h1>hi</h1>");

    const discovered = storage.discoverRunArtifacts(scope);

    expect(discovered.map((artifact) => artifact.displayName)).toEqual(["answer.md", "site"]);
    expect(discovered[0]?.contentHash).toMatch(/^sha256:/);
    expect(discovered[1]).toMatchObject({
      kind: "directory",
      mimeType: "inode/directory",
      contentHash: null,
      sizeBytes: null,
    });
  });

  it("isolates same-name artifacts across runs in the same session", () => {
    const temp = mkdtempSync(join(tmpdir(), "omi-artifacts-"));
    const root = join(temp, "Artifacts");
    const storage = new OmiArtifactStorage({ rootDir: root });
    const firstScope = {
      ownerId: "owner-1",
      sessionId: "session-1",
      runId: "run-1",
      attemptId: "attempt-1",
    };
    const secondScope = {
      ownerId: "owner-1",
      sessionId: "session-1",
      runId: "run-2",
      attemptId: "attempt-1",
    };
    writeFileSync(join(storage.prepareRunDirectory(firstScope), "answer.md"), "first");
    writeFileSync(join(storage.prepareRunDirectory(secondScope), "answer.md"), "second");

    const first = storage.discoverRunArtifacts(firstScope);
    const second = storage.discoverRunArtifacts(secondScope, first);

    expect(first).toHaveLength(1);
    expect(second).toHaveLength(1);
    expect(first[0]?.uri).toContain("/run-1/attempt-1/answer.md");
    expect(second[0]?.uri).toContain("/run-2/attempt-1/answer.md");
    expect(readFileSync(new URL(first[0]!.uri), "utf8")).toBe("first");
    expect(readFileSync(new URL(second[0]!.uri), "utf8")).toBe("second");
  });

  it("leaves user-specified external locations alone", () => {
    const temp = mkdtempSync(join(tmpdir(), "omi-artifacts-"));
    const source = join(temp, "keep.txt");
    writeFileSync(source, "hello");
    const uri = pathToFileURL(source).toString();

    const storage = new OmiArtifactStorage({ rootDir: join(temp, "Artifacts") });
    const normalized = storage.normalizeArtifact(
      {
        kind: "file",
        role: "result",
        uri,
        metadata: { userSpecifiedPath: true },
      },
      {
        ownerId: "owner-1",
        sessionId: "session-1",
        runId: "run-1",
        attemptId: "attempt-1",
      }
    );

    expect(normalized.uri).toBe(uri);
  });

  it("derives artifact root beside the per-bundle runtime state directory", () => {
    const root = defaultArtifactRoot({
      OMI_AGENT_STATE_DIR: "/Users/me/Library/Application Support/Omi/AgentRuntime/com.omi.omi-test",
    } as NodeJS.ProcessEnv);

    expect(root).toBe("/Users/me/Library/Application Support/Omi/Artifacts/com.omi.omi-test");
  });
});
