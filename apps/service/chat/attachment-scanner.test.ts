import { describe, expect, test } from "bun:test";

import {
  advanceAttachmentScan,
  ATTACHMENT_SCAN_TIMEOUT_MS,
  beginAttachmentScan,
  DEV_NOOP_SCANNER_ID,
} from "./attachment-scanner";
import { createInMemoryChatAttachmentsStore } from "../stores/chat-attachments-store";
import { ATTACHMENT_STAGING_TTL_MS, MAIN_CHAT_ATTACHMENT_SCOPE } from "./attachment-policy";

const pdf = new Uint8Array([0x25, 0x50, 0x44, 0x46, 0x2d, 0x31, 0x2e, 0x37, 0x0a]);

describe("dev-noop-scanner attachment lifecycle", () => {
  test("staged advances to clean and only clean attachments bind", () => {
    const store = createInMemoryChatAttachmentsStore();
    const now = { value: 1_000 };
    const clock = { now: () => now.value };
    const staged = store.stage({
      id: "scan-1",
      contentReference: "ref-1",
      accountId: "owner",
      scope: MAIN_CHAT_ATTACHMENT_SCOPE,
      displayName: "note.pdf",
      mimeType: "application/pdf",
      content: pdf,
      stagedAt: now.value,
      stageExpiresAt: now.value + ATTACHMENT_STAGING_TTL_MS,
    });
    expect(staged.state).toBe("staged");
    expect(staged.scannerId).toBe(DEV_NOOP_SCANNER_ID);
    const scanning = store.advanceScan(staged.id, clock)!;
    expect(scanning.state).toBe("scanning");
    const clean = store.advanceScan(staged.id, clock)!;
    expect(clean.state).toBe("clean");
    expect(store.bindToMessage({
      accountId: "owner",
      scope: MAIN_CHAT_ATTACHMENT_SCOPE,
      attachmentIds: ["scan-1"],
      messageId: "message-1",
      nowEpochMilliseconds: now.value,
      contentExpiresAt: now.value + ATTACHMENT_STAGING_TTL_MS,
    }).kind).toBe("ready");
    expect(store.bindToMessage({
      accountId: "owner",
      scope: MAIN_CHAT_ATTACHMENT_SCOPE,
      attachmentIds: ["scan-1"],
      messageId: "message-2",
      nowEpochMilliseconds: now.value,
      contentExpiresAt: now.value + ATTACHMENT_STAGING_TTL_MS,
    }).kind).toBe("not_found");
  });

  test("timed_out fail-closed bind and retry re-enters scanning", () => {
    const store = createInMemoryChatAttachmentsStore();
    const now = { value: 5_000 };
    const clock = { now: () => now.value };
    store.stage({
      id: "scan-timeout",
      contentReference: "ref-timeout",
      accountId: "owner",
      scope: MAIN_CHAT_ATTACHMENT_SCOPE,
      displayName: "late.pdf",
      mimeType: "application/pdf",
      content: pdf,
      stagedAt: now.value,
      stageExpiresAt: now.value + ATTACHMENT_STAGING_TTL_MS,
    });
    store.advanceScan("scan-timeout", clock);
    now.value += ATTACHMENT_SCAN_TIMEOUT_MS;
    const timedOut = store.advanceScan("scan-timeout", clock)!;
    expect(timedOut.state).toBe("timed_out");
    expect(store.bindToMessage({
      accountId: "owner",
      scope: MAIN_CHAT_ATTACHMENT_SCOPE,
      attachmentIds: ["scan-timeout"],
      messageId: "message-timeout",
      nowEpochMilliseconds: now.value,
      contentExpiresAt: now.value + ATTACHMENT_STAGING_TTL_MS,
    }).kind).toBe("not_found");
    const retried = store.retryScan("scan-timeout", clock)!;
    expect(retried.state).toBe("clean");
    expect(store.removeUnbound("scan-timeout", "owner")).toBe(true);
  });

  test("scanner module rejects bound rescans and retry re-enters from rejected", () => {
    expect(() => beginAttachmentScan({
      scannerId: DEV_NOOP_SCANNER_ID,
      state: "bound",
      scanningStartedAt: null,
      stagedAt: 0,
    }, { clock: { now: () => 0 } })).toThrow("bound attachments are not scannable");
    const restarted = beginAttachmentScan({
      scannerId: DEV_NOOP_SCANNER_ID,
      state: "rejected",
      scanningStartedAt: 1,
      stagedAt: 0,
    }, { clock: { now: () => 2 } });
    expect(restarted.state).toBe("scanning");
    expect(advanceAttachmentScan({
      ...restarted,
      scannerId: DEV_NOOP_SCANNER_ID,
      stagedAt: 0,
    }, { clock: { now: () => 2 } }).state).toBe("clean");
  });
});
