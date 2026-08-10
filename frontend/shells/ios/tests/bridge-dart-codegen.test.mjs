import assert from "node:assert/strict";
import { cpSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import test from "node:test";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const core = path.resolve(here, "../../..");
const generator = path.join(core, "scripts/gen-bridge-dart.mjs");
const sources = [
  "contracts/src/bridge/http.ts",
  "contracts/src/bridge/stream.ts",
  "contracts/src/bridge/chat-attachment-staging.ts",
  "contracts/ratified/src/projections/synthesized.ts",
];

function run(root, check = false) {
  return spawnSync(process.execPath, [generator, ...(check ? ["--check"] : [])], {
    cwd: core,
    encoding: "utf8",
    env: {
      ...process.env,
      OMI_BRIDGE_DART_CONTRACT_ROOT: root,
      OMI_IOS_SHELL_DIR: path.join(root, "shell"),
    },
  });
}

test("Dart bindings drift on every native stream and staging protocol symbol class", () => {
  const root = mkdtempSync(path.join(tmpdir(), "omi-bridge-dart-drift-"));
  try {
    for (const source of sources) {
      const destination = path.join(root, source);
      mkdirSync(path.dirname(destination), { recursive: true });
      cpSync(path.join(core, source), destination);
    }
    mkdirSync(path.join(root, "shell/app/lib/gen"), { recursive: true });
    const generated = run(root);
    assert.equal(generated.status, 0, generated.stderr || generated.stdout);

    const mutations = [
      ["contracts/src/bridge/stream.ts", '"omiStream"', '"omiStreamChanged"'],
      ["contracts/src/bridge/stream.ts", '"__omiStreamFrame"', '"__omiStreamFrameChanged"'],
      ["contracts/src/bridge/stream.ts", '"chat-generation-events"', '"chat-generation-events-changed"'],
      ["contracts/src/bridge/stream.ts", 't: "open"', 't: "open-changed"'],
      ["contracts/src/bridge/stream.ts", 't: "grant"', 't: "grant-changed"'],
      ["contracts/src/bridge/stream.ts", 't: "cancel"', 't: "cancel-changed"'],
      ["contracts/src/bridge/stream.ts", 't: "data"', 't: "data-changed"'],
      ["contracts/src/bridge/stream.ts", 't: "end"', 't: "end-changed"'],
      ["contracts/src/bridge/stream.ts", 't: "error"', 't: "error-changed"'],
      ["contracts/src/bridge/stream.ts", "lastEventId?: string", "resumeCursor?: string"],
      ["contracts/src/bridge/chat-attachment-staging.ts", '"omiChatAttachmentStaging"', '"omiChatAttachmentStagingChanged"'],
      ["contracts/src/bridge/chat-attachment-staging.ts", '"__omiChatAttachmentStagingReply"', '"__omiChatAttachmentStagingReplyChanged"'],
      ["contracts/src/bridge/chat-attachment-staging.ts", 't: "pick-and-stage"', 't: "pick-and-stage-changed"'],
      ["contracts/src/bridge/chat-attachment-staging.ts", '| "cancelled"', '| "cancelled-changed"'],
      ["contracts/src/bridge/chat-attachment-staging.ts", "mimeType: string", "mediaType: string"],
    ];

    for (const [relative, before, after] of mutations) {
      const target = path.join(root, relative);
      const original = readFileSync(path.join(core, relative), "utf8");
      assert.ok(original.includes(before), `fixture mutation target disappeared: ${before}`);
      writeFileSync(target, original.replace(before, after));
      const drift = run(root, true);
      assert.equal(drift.status, 1, `${relative}: ${before}\n${drift.stdout}\n${drift.stderr}`);
      assert.match(drift.stderr, /bridge dart drift/);
      writeFileSync(target, original);
    }
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
