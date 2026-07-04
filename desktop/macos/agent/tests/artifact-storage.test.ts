import { mkdtempSync, readFileSync, writeFileSync } from "node:fs";
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
    expect(normalized.uri).toContain("/run-1/answer.txt");
    expect(normalized.metadata).toMatchObject({
      omiManaged: true,
      originalUri: pathToFileURL(source).toString(),
    });
    expect(normalized.contentHash).toMatch(/^sha256:/);
    expect(readFileSync(new URL(normalized.uri), "utf8")).toBe("hello");
    expect(readFileSync(join(root, "owner-1", new Date().toISOString().slice(0, 10), "run-1", "manifest.json"), "utf8"))
      .toContain("originalUri");
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
