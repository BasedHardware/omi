import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { cpSync, mkdtempSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";

const shellRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const coreRoot = resolve(shellRoot, "../..");
const generator = join(coreRoot, "scripts/gen-bridge-swift.mjs");
const outputRelative = "shell/Sources/OmiShell/BridgeHttpContract.generated.swift";

const contractFiles = [
  "contracts/src/bridge/http.ts",
  "contracts/src/bridge/stream.ts",
  "contracts/src/bridge/chat-attachment-staging.ts",
  "contracts/ratified/src/projections/synthesized.ts",
  "contracts/ratified/package.json",
];

function makeFixture() {
  const scratch = mkdtempSync(join(tmpdir(), "omi-swift-chat-bindings-"));
  const fixtureCore = join(scratch, "core");
  const fixtureShell = join(scratch, "macos");
  for (const relative of contractFiles) {
    const destination = join(fixtureCore, relative);
    mkdirSync(dirname(destination), { recursive: true });
    cpSync(join(coreRoot, relative), destination);
  }
  const generated = join(fixtureShell, outputRelative);
  mkdirSync(dirname(generated), { recursive: true });
  cpSync(join(shellRoot, outputRelative), generated);
  return { scratch, fixtureCore, fixtureShell };
}

function checkFixture(fixture) {
  return spawnSync(process.execPath, [generator, "--check"], {
    encoding: "utf8",
    env: {
      ...process.env,
      OMI_CORE_ROOT: fixture.fixtureCore,
      OMI_MACOS_SHELL_DIR: fixture.fixtureShell,
    },
  });
}

test("generated Swift binds the exact stream, staging, and P7 host vocabulary", () => {
  const generated = readFileSync(join(shellRoot, outputRelative), "utf8");
  for (const expected of [
    'static let channel = "omiStream"',
    'static let sinkFunction = "__omiStreamFrame"',
    'static let chatGenerationChannel = "chat-generation-events"',
    'static let chatAgentRunChannel = "chat-agent-run-events"',
    'case open = "open"',
    'case grant = "grant"',
    'case cancel = "cancel"',
    'case data = "data"',
    'case end = "end"',
    'case error = "error"',
    'static let channel = "omiChatAttachmentStaging"',
    'static let replyFunction = "__omiChatAttachmentStagingReply"',
    'case unavailable = "unavailable"',
    '"mimeType"',
    '"sizeBytes"',
    '"expiresAt"',
    'static let contractVersionHeader = "x-omi-contract-version"',
    'static let contractVersion = "1.0.0"',
  ]) assert.ok(generated.includes(expected), `generated Swift omitted ${expected}`);

  execFileSync(process.execPath, [generator, "--check"], { cwd: coreRoot, stdio: "pipe" });
});

test("every extracted stream/staging symbol or descriptor change reddens Swift drift", () => {
  const mutations = [
    ["contracts/src/bridge/stream.ts", '"omiStream"', '"omiStreamChanged"'],
    ["contracts/src/bridge/stream.ts", '"__omiStreamFrame"', '"__omiStreamFrameChanged"'],
    ["contracts/src/bridge/stream.ts", '"chat-generation-events"', '"chat-generation-events-changed"'],
    ["contracts/src/bridge/stream.ts", '"chat-agent-run-events"', '"chat-agent-run-events-changed"'],
    ["contracts/src/bridge/stream.ts", '{ t: "open"', '{ t: "opened"'],
    ["contracts/src/bridge/chat-attachment-staging.ts", '"omiChatAttachmentStaging"', '"omiChatAttachmentStagingChanged"'],
    ["contracts/src/bridge/chat-attachment-staging.ts", '"__omiChatAttachmentStagingReply"', '"__omiChatAttachmentStagingReplyChanged"'],
    ["contracts/src/bridge/chat-attachment-staging.ts", 't: "pick-and-stage"', 't: "pick-and-stage-changed"'],
    ["contracts/src/bridge/chat-attachment-staging.ts", '| "unavailable"', '| "host-unavailable"'],
    ["contracts/src/bridge/chat-attachment-staging.ts", 'mimeType: string;', 'serverMimeType: string;'],
    [
      "contracts/ratified/src/projections/synthesized.ts",
      'SYNTHESIZED_READ_CONTRACT_VERSION = "1.0.0"',
      'SYNTHESIZED_READ_CONTRACT_VERSION = "1.0.1"',
    ],
  ];
  for (const [relative, before, after] of mutations) {
    const fixture = makeFixture();
    try {
      const file = join(fixture.fixtureCore, relative);
      const source = readFileSync(file, "utf8");
      assert.ok(source.includes(before), `mutation precondition missing: ${before}`);
      writeFileSync(file, source.replace(before, after));
      const result = checkFixture(fixture);
      assert.notEqual(result.status, 0, `${relative} mutation did not cause drift`);
      assert.match(result.stderr, /bridge swift drift:/);
    } finally {
      rmSync(fixture.scratch, { recursive: true, force: true });
    }
  }
  // red-proof: each mutation above leaves the checked-in Swift untouched and
  // the real generator exits 1 with `bridge swift drift:`.
});

test("ratified package release version is not the executable app wire version", () => {
  const fixture = makeFixture();
  try {
    const packageFile = join(fixture.fixtureCore, "contracts/ratified/package.json");
    const source = readFileSync(packageFile, "utf8");
    assert.match(source, /"version": "0\.8\.0"/);
    writeFileSync(packageFile, source.replace('"version": "0.8.0"', '"version": "99.0.0"'));
    const result = checkFixture(fixture);
    assert.equal(result.status, 0, `${result.stdout}${result.stderr}`);
  } finally {
    rmSync(fixture.scratch, { recursive: true, force: true });
  }
});
