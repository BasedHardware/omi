import { describe, expect, test } from "bun:test";

import {
  parseUserAssertedStmNote,
  sealUserAssertedStmNote,
  stmNoteFormationWorkId,
  stmNoteId,
} from "./note";

const metadata = (overrides: Record<string, unknown> = {}) => Object.freeze({
  write_door: "mcp" as const,
  client_write_ref: "client-write:one",
  submitted_at: "2026-08-13T18:00:00.000Z",
  ...overrides,
});

const noteInput = (overrides: Record<string, unknown> = {}) => ({
  owner_account_id: "account:alice",
  write_id: "write:one",
  content: "Met Alex at the product launch.",
  metadata: metadata(),
  ...overrides,
});

describe("user asserted stm note", () => {
  test("seals stable note and formation work coordinates from owner plus write id", () => {
    const first = sealUserAssertedStmNote(noteInput());
    const replay = sealUserAssertedStmNote(noteInput());
    const changedContent = sealUserAssertedStmNote(noteInput({ content: "Met Alex again." }));

    expect(replay).toEqual(first);
    expect(first.note_id).toBe(stmNoteId("account:alice", "write:one"));
    expect(first.formation_work_id).toBe(stmNoteFormationWorkId("account:alice", "write:one"));
    expect(changedContent.formation_work_id).toBe(first.formation_work_id);
    expect(changedContent.note_id).toBe(first.note_id);
    expect(changedContent.content_digest).not.toBe(first.content_digest);
    expect(changedContent.note_digest).not.toBe(first.note_digest);
  });

  test("rejects proxy, accessor, and malformed metadata", () => {
    expect(() => sealUserAssertedStmNote(new Proxy(noteInput(), {}))).toThrow("invalid_input");
    expect(() => sealUserAssertedStmNote({
      ...noteInput(),
      get content() { return "x"; },
    })).toThrow("invalid_input");
    expect(() => sealUserAssertedStmNote(noteInput({
      metadata: metadata({ write_door: "sms" }),
    }))).toThrow("invalid_metadata");
    expect(() => sealUserAssertedStmNote(noteInput({ content: "" }))).toThrow("invalid_input");
  });

  test("parse round-trips an already sealed note", () => {
    const sealed = sealUserAssertedStmNote(noteInput());
    expect(parseUserAssertedStmNote(sealed)).toEqual(sealed);
    expect(() => parseUserAssertedStmNote({ ...sealed, note_digest: "0".repeat(64) }))
      .toThrow("note_digest_mismatch");
  });
});
