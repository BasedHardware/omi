import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import test from "node:test";
import {
  attachmentCapState,
  mergeOlderPage,
  messageKey,
  reconcileMessages,
} from "../src/production/chat-reconcile.ts";
import {
  ATTACHMENT_SCAN_TIMEOUT_MS,
  DEV_NOOP_SCANNER_ID,
  asScanTerminal,
  attachmentsAreAdmissibleForSend,
  canRemoveTrayAttachment,
  canRetryAttachmentScan,
  createDevNoopAttachmentScanner,
  isAdmissibleForBind,
  scanMetadataFromWire,
  toTrayAttachment,
} from "../src/production/chat-attachment-scan.ts";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const read = (relative) => readFile(resolve(root, relative), "utf8");

function canonical(serverId, text, clientMessageId = null) {
  return {
    role: "user",
    text,
    delivery: { kind: "canonical", serverId, clientMessageId, generationOutcome: null },
    attachments: [],
  };
}

function echo(clientMessageId, text) {
  return {
    role: "user",
    text,
    delivery: { kind: "echo", clientMessageId },
    attachments: [],
  };
}

function failed(generationId, text, retryable = true) {
  return {
    role: "assistant",
    text,
    delivery: { kind: "failed", generationId, clientMessageId: "failed-client", source: "provider", retryable },
    attachments: [],
  };
}

test("echo is replaced in place by the matching canonical server message", () => {
  // red-proof: making reconcileMessages concatenate instead of replace yields three
  // messages and fails the canonical serverId assertion below.
  const local = [
    canonical("s1", "earlier"),
    echo("c1", "hi"),
  ];
  const incoming = [
    canonical("s1", "earlier"),
    canonical("s9", "hi", "c1"),
  ];
  const result = reconcileMessages(local, incoming);
  assert.equal(result[1]?.delivery.kind, "canonical");
  assert.equal(result[1]?.delivery.serverId, "s9");
  assert.equal(result[1]?.delivery.clientMessageId, "c1");
  assert.equal(result.filter((message) => message.text === "hi").length, 1);
  assert.equal(messageKey(result[1]), messageKey(local[1]));
});

test("reconcile preserves server order and never client-sorts", () => {
  // red-proof: sorting by any client-side field (text/serverId) must fail the
  // asserted zebra→apple→mango text sequence (alphabetical would be apple→mango→zebra).
  const incoming = [
    canonical("s-m1", "zebra"),
    canonical("s-m2", "apple"),
    canonical("s-m3", "mango"),
  ];
  const local = [
    canonical("s-m3", "mango"),
    canonical("s-m1", "zebra"),
    canonical("s-m2", "apple"),
  ];
  const result = reconcileMessages(local, incoming);
  assert.deepEqual(result.map((message) => message.text), ["zebra", "apple", "mango"]);
});

test("older-page merge is idempotent and does not reorder", () => {
  // red-proof: an unconditional prepend must fail the second-merge text sequence.
  const current = [
    canonical("s-current-1", "now-a"),
    canonical("s-current-2", "now-b"),
  ];
  const older = {
    messages: [
      canonical("s-older-1", "old-a"),
      canonical("s-older-2", "old-b"),
    ],
    hasOlder: false,
    olderCursor: null,
  };
  const once = mergeOlderPage(current, older);
  const twice = mergeOlderPage(once, older);
  assert.deepEqual(once.map((message) => message.text), ["old-a", "old-b", "now-a", "now-b"]);
  assert.deepEqual(twice.map((message) => message.text), ["old-a", "old-b", "now-a", "now-b"]);
});

test("unreported attachment cap disables the attach affordance", () => {
  // red-proof: defaulting a missing cap to any number must fail this exact shape.
  assert.deepEqual(
    attachmentCapState({
      maxAttachmentsPerMessage: null,
      maxAttachmentBytes: null,
      allowedAttachmentMimeTypes: null,
    }, 0),
    { enabled: false, atLimit: false, reason: "unknown-cap" },
  );
});

test("failed generation projections have stable generation identity", () => {
  const message = failed("generation-fail", "partial response");
  assert.equal(messageKey(message), "generation:generation-fail");
  assert.equal(message.delivery.kind, "failed");
  assert.equal(message.delivery.retryable, true);
});

test("cancelled canonical delivery is distinct from completed and retains text", () => {
  // red-proof: collapse generationOutcome to a completed boolean or discard
  // the cancelled row. The discriminant/text assertions fail.
  const cancelled = {
    role: "assistant",
    text: "Retained partial",
    delivery: {
      kind: "canonical",
      serverId: "assistant-partial-1",
      clientMessageId: null,
      generationOutcome: "cancelled",
    },
    attachments: [],
  };
  const completed = {
    ...cancelled,
    delivery: { ...cancelled.delivery, generationOutcome: "completed" },
  };
  assert.notEqual(cancelled.delivery.generationOutcome, completed.delivery.generationOutcome);
  assert.equal(cancelled.text, "Retained partial");
});

test("ChatProduction avoids numeric attachment literals and fixture imports", async () => {
  const source = await read("src/production/ChatProduction.tsx");
  assert.doesNotMatch(source, /maxAttachmentsPerMessage\s*[:=]\s*\d+/);
  assert.doesNotMatch(source, /attachmentCapState\(\s*\{[^}]*\d+/);
  assert.doesNotMatch(source, /from\s+["']\.\/chat-fixtures/);
  assert.doesNotMatch(source, /FIXTURE_SERVER_ATTACHMENT_CAP|\battach(?:ments?)?\s*[:=]\s*\d+/i);
  assert.match(source, /attachmentCapState\(capabilities/);
  assert.match(source, /data-route="chat"/);
  assert.match(source, /surface-notices/);
  assert.match(source, /data-attachment-scan/);
  assert.match(source, /scanMetadataFromWire/);
  assert.doesNotMatch(source, /antivirus|\bmalware\b|\bvirus\b/i);
  const scanSource = await read("src/production/chat-attachment-scan.ts");
  assert.match(scanSource, /"dev-noop-scanner"/);
  assert.match(scanSource, /ATTACHMENT_SCAN_TIMEOUT_MS = 5_000/);
  // The chrome route union was widened by FE-SURFACES, so Chat now marks itself active
  // rather than borrowing Home's highlight. Chat is deliberately not a visible nav
  // destination yet — where it sits is a chrome design decision, not a surface author's.
  assert.match(source, /<ProductionChrome locale=\{locale\} active="chat"/);
  assert.doesNotMatch(source, /active="home"/);
});

test("dev-noop-scanner is fail-closed and times out on an injected clock", async () => {
  // red-proof: treating any non-clean state as admissible, or reading Date.now(),
  // must fail the exact terminal and timeout assertions below.
  const staged = {
    id: "opaque-scan",
    mimeType: "application/pdf",
    sizeBytes: 100,
    expiresAt: "2026-08-11T12:00:00.000Z",
    state: "staged",
  };
  assert.equal(DEV_NOOP_SCANNER_ID, "dev-noop-scanner");
  assert.equal(isAdmissibleForBind("clean"), true);
  assert.equal(isAdmissibleForBind("scanning"), false);
  assert.equal(isAdmissibleForBind("staged"), false);
  assert.equal(isAdmissibleForBind("rejected"), false);
  assert.equal(isAdmissibleForBind("timed_out"), false);
  assert.equal(isAdmissibleForBind("error"), false);
  assert.equal(isAdmissibleForBind("bound"), false);
  assert.equal(canRetryAttachmentScan("rejected"), true);
  assert.equal(canRetryAttachmentScan("timed_out"), true);
  assert.equal(canRetryAttachmentScan("error"), true);
  assert.equal(canRetryAttachmentScan("scanning"), false);
  assert.equal(canRetryAttachmentScan("clean"), false);
  assert.equal(canRetryAttachmentScan("bound"), false);
  assert.equal(canRemoveTrayAttachment("bound"), false);
  assert.equal(canRemoveTrayAttachment("scanning"), true);
  assert.equal(canRemoveTrayAttachment("error"), true);
  assert.equal(asScanTerminal("clean"), "clean");
  assert.equal(asScanTerminal("antivirus-clean"), null);
  assert.equal(asScanTerminal("bound"), null);
  const tray = toTrayAttachment(staged, "scanning");
  assert.equal(tray.scannerId, "dev-noop-scanner");
  assert.equal(tray.scanState, "scanning");
  assert.equal(tray.state, "staged");
  assert.equal(attachmentsAreAdmissibleForSend([tray]), false);
  assert.equal(attachmentsAreAdmissibleForSend([{ ...tray, scanState: "clean" }]), true);

  const scanner = createDevNoopAttachmentScanner();
  assert.equal(scanner.identity, "dev-noop-scanner");
  assert.equal(await scanner.scan(staged), "clean");

  let now = 0;
  const clock = { now: () => now };
  const timed = createDevNoopAttachmentScanner({ clock, startedAt: 0 });
  assert.equal(await timed.scan(staged), "clean");
  now = ATTACHMENT_SCAN_TIMEOUT_MS;
  assert.equal(await timed.scan(staged), "timed_out");

  const wire = scanMetadataFromWire({
    ...staged,
    scanState: "clean",
    scannerId: "dev-noop-scanner",
  });
  assert.deepEqual(wire, { scanState: "clean", scannerId: "dev-noop-scanner" });
  assert.equal(scanMetadataFromWire({ ...staged, scanState: "antivirus-clean" }).scanState, null);
  assert.equal(isAdmissibleForBind(wire.scanState ?? "error"), true);
});
