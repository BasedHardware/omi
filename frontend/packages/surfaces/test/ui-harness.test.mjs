import assert from "node:assert/strict";
import { mkdirSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

import { generateManifest } from "../scripts/lib/ui-harness-catalog.mjs";
import {
  assertCaptureSummary,
  CAPTURE_SUMMARY_SCHEMA,
  DIFF_METHOD,
  encodeRgbaPng,
  isCaptureSummary,
  writePngFile,
} from "../scripts/lib/ui-harness-png.mjs";
import { diffRuns } from "../scripts/lib/ui-harness-run.mjs";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFileSync(resolve(root, relative), "utf8");

function quotedStrings(source, name) {
  const match = source.match(new RegExp(`export const ${name} = \\[([\\s\\S]*?)\\] as const`));
  assert.ok(match, `missing ${name}`);
  return [...match[1].matchAll(/"([^"]+)"/g)].map((item) => item[1]);
}

function polishDomainStates(source, domain) {
  const match = source.match(new RegExp(`${domain}: \\[([^\\]]+)\\]`));
  assert.ok(match, `missing polish domain ${domain}`);
  return [...match[1].matchAll(/"([^"]+)"/g)].map((item) => item[1]);
}

function fillRgba(width, height, rgba) {
  const buffer = Buffer.alloc(width * height * 4);
  for (let pixel = 0; pixel < width * height; pixel += 1) buffer.set(rgba, pixel * 4);
  return buffer;
}

function writeRun(dir, entries) {
  mkdirSync(dir, { recursive: true });
  const summary = {
    schema: CAPTURE_SUMMARY_SCHEMA,
    mode: "browser",
    origin: "http://127.0.0.1:4650",
    outDir: dir,
    startedAt: "2026-08-15T00:00:00.000Z",
    finishedAt: "2026-08-15T00:00:01.000Z",
    wallClockMs: 1000,
    count: entries.length,
    errorCount: 0,
    entries: entries.map((entry) => ({
      id: entry.id,
      url: `http://127.0.0.1:4650/${entry.id}`,
      bytes: entry.bytes,
      viewport: { width: entry.width, height: entry.height },
      renderMs: 1,
      consoleErrors: [],
    })),
  };
  writeFileSync(join(dir, "summary.json"), `${JSON.stringify(summary, null, 2)}\n`);
  return summary;
}

test("generated manifest enumerates every lab surface state platform locale and polish flag", async () => {
  const [lab, catalog, memories, conversations, tasks, propositions, chat, settings, screen, polish] = [
    read("src/lab/main.tsx"),
    read("src/lab/catalog.ts"),
    read("src/production/memory-fixtures.ts"),
    read("src/production/conversation-fixtures.ts"),
    read("src/production/task-fixtures.ts"),
    read("src/production/proposition-fixtures.ts"),
    read("src/production/chat-fixtures.ts"),
    read("src/production/settings-fixtures.ts"),
    read("src/production/screen-fixtures.ts"),
    read("src/production/polish-evidence-fixtures.ts"),
  ];
  const manifest = await generateManifest("http://127.0.0.1:4650");
  const ids = new Set(manifest.states.map((entry) => entry.id));
  const expected = [];
  const surfaces = [
    ["memories", quotedStrings(memories, "FIXTURE_STATES"), false],
    ["conversations", quotedStrings(conversations, "CONVERSATION_FIXTURE_STATES"), false],
    ["conversation-detail", quotedStrings(conversations, "CONVERSATION_FIXTURE_STATES"), false],
    ["tasks", quotedStrings(tasks, "FIXTURE_STATES"), false],
    ["memories-platform", quotedStrings(propositions, "PROPOSITION_FIXTURE_STATES"), false],
    ["chat", quotedStrings(chat, "CHAT_FIXTURE_STATES"), false],
    ["settings", quotedStrings(settings, "SETTINGS_FIXTURE_STATES"), false],
    ["folders", polishDomainStates(polish, "folders"), true],
    ["listen", polishDomainStates(polish, "listen"), true],
    ["rewind", quotedStrings(screen, "SCREEN_FIXTURE_STATES"), false],
  ];
  const matrix = [
    ["memories-platform", polishDomainStates(polish, "memories"), true],
    ["tasks", polishDomainStates(polish, "tasks"), true],
    ["conversations", polishDomainStates(polish, "conversations"), true],
    ["folders", polishDomainStates(polish, "folders"), true],
    ["chat", polishDomainStates(polish, "chat"), true],
    ["listen", polishDomainStates(polish, "listen"), true],
    ["settings", polishDomainStates(polish, "settings"), true],
  ];
  for (const [surface, states, polishFlag] of [...surfaces, ...matrix]) {
    for (const state of states) {
      for (const platform of ["mobile", "desktop"]) {
        expected.push(`${surface}.${state}.${platform}.en-US.${polishFlag ? "polish" : "raw"}`);
      }
    }
  }
  const uniqueExpected = [...new Set(expected)];
  for (const id of uniqueExpected) {
    assert.equal(ids.has(id), true, `manifest missing ${id}`);
  }
  assert.equal(manifest.count, uniqueExpected.length);
  assert.equal(manifest.states.length, uniqueExpected.length);
  assert.match(lab, /from "\.\/catalog\.js"/);
  assert.match(catalog, /states: MEMORY_STATES/);
  assert.match(catalog, /POLISH_EVIDENCE_STATES\.settings/);
  assert.doesNotMatch(catalog, /bridgeHttpClient|openWebStorageBridge|fetch\(/);
  const locked = manifest.states.find((entry) => entry.id === "memories.locked.desktop.en-US.raw");
  assert.ok(locked);
  assert.equal(locked.path, "?qa=memories&state=locked&platform=desktop&locale=en-US");
  assert.equal(locked.polish, false);
  const polishSettings = manifest.states.find((entry) => entry.id === "settings.ready.desktop.en-US.polish");
  assert.ok(polishSettings);
  assert.match(polishSettings.path, /polish=1/);
  // red-proof: adding a quoted state to a lab fixture array without catalog
  // importing that array, or dropping the state from enumerateLabStates, makes
  // uniqueExpected contain an id that ids.has() rejects.
});

test("capture summary shape accepts a complete run document and rejects a silent error omission", () => {
  const valid = {
    schema: CAPTURE_SUMMARY_SCHEMA,
    mode: "browser",
    origin: "http://127.0.0.1:4650",
    outDir: "/tmp/ui-harness",
    startedAt: "2026-08-15T00:00:00.000Z",
    finishedAt: "2026-08-15T00:00:02.000Z",
    wallClockMs: 2000,
    count: 1,
    errorCount: 1,
    entries: [{
      id: "memories.normal.desktop.en-US.raw",
      url: "http://127.0.0.1:4650/?qa=memories&state=normal&platform=desktop&locale=en-US",
      bytes: 1200,
      viewport: { width: 1280, height: 800 },
      renderMs: 40,
      consoleErrors: ["TypeError: boom"],
    }],
  };
  assert.equal(isCaptureSummary(valid), true);
  assert.equal(assertCaptureSummary(valid), valid);
  const missingErrors = structuredClone(valid);
  delete missingErrors.entries[0].consoleErrors;
  assert.equal(isCaptureSummary(missingErrors), false);
  assert.throws(() => assertCaptureSummary(missingErrors), /not a valid/);
  // red-proof: dropping consoleErrors from a state that logged lets a capture
  // look clean; the shape gate refuses that document.
});

test("diff reports no changes for identical runs and only the altered id when one pixel region changes", () => {
  const scratch = mkdtempSync(join(tmpdir(), "omi-ui-harness-diff-"));
  try {
    const beforeDir = join(scratch, "before");
    const afterSame = join(scratch, "after-same");
    const afterChanged = join(scratch, "after-changed");
    mkdirSync(beforeDir, { recursive: true });
    mkdirSync(afterSame, { recursive: true });
    mkdirSync(afterChanged, { recursive: true });
    const red = fillRgba(8, 8, [200, 16, 16, 255]);
    const blue = fillRgba(8, 8, [200, 16, 16, 255]);
    for (let y = 2; y < 6; y += 1) {
      for (let x = 2; x < 6; x += 1) blue.set([16, 16, 200, 255], (y * 8 + x) * 4);
    }
    const unchangedId = "tasks.empty.desktop.en-US.raw";
    const changedId = "memories.normal.desktop.en-US.raw";
    for (const dir of [beforeDir, afterSame, afterChanged]) {
      writePngFile(join(dir, `${unchangedId}.png`), 8, 8, red);
    }
    writePngFile(join(beforeDir, `${changedId}.png`), 8, 8, red);
    writePngFile(join(afterSame, `${changedId}.png`), 8, 8, Buffer.from(red));
    writePngFile(join(afterChanged, `${changedId}.png`), 8, 8, blue);
    const beforeBytes = encodeRgbaPng(8, 8, red).length;
    writeRun(beforeDir, [
      { id: unchangedId, bytes: beforeBytes, width: 8, height: 8 },
      { id: changedId, bytes: beforeBytes, width: 8, height: 8 },
    ]);
    writeRun(afterSame, [
      { id: unchangedId, bytes: beforeBytes, width: 8, height: 8 },
      { id: changedId, bytes: beforeBytes, width: 8, height: 8 },
    ]);
    writeRun(afterChanged, [
      { id: unchangedId, bytes: beforeBytes, width: 8, height: 8 },
      { id: changedId, bytes: encodeRgbaPng(8, 8, blue).length, width: 8, height: 8 },
    ]);

    const identical = diffRuns(beforeDir, afterSame);
    assert.equal(identical.method, DIFF_METHOD);
    assert.equal(identical.changedCount, 0);
    assert.deepEqual(identical.changed, []);
    assert.equal(identical.unchanged.length, 2);

    const altered = diffRuns(beforeDir, afterChanged);
    assert.equal(altered.changedCount, 1);
    assert.equal(altered.changed[0].id, changedId);
    assert.equal(altered.changed[0].changedPixels, 16);
    assert.equal(altered.changed[0].totalPixels, 64);
    assert.ok(readFileSync(altered.changed[0].sideBySide).subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a])));
    assert.equal(altered.unchanged.includes(unchangedId), true);
    assert.equal(altered.changed.some((entry) => entry.id === unchangedId), false);
    // red-proof: reporting the untouched id, or missing the 4×4 blue patch,
    // fails the changed-id and changedPixels assertions.
  } finally {
    rmSync(scratch, { recursive: true, force: true });
  }
});
