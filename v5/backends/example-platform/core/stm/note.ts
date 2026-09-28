import { isProxy } from "node:util/types";

import { sha256CanonicalContent } from "../retrieve/content-digest";

export const USER_ASSERTED_STM_NOTE_VERSION = "user-asserted-stm-note-v1" as const;
export const STM_NOTE_SOURCE_SCHEMA_VERSION = "integrator-stm-note-source-v1" as const;

export type StmNoteWriteDoor = "http" | "mcp" | "mcp_legacy";

export interface UserAssertedStmNoteMetadata {
  readonly write_door: StmNoteWriteDoor;
  readonly client_write_ref: string | null;
  readonly submitted_at: string;
}

export interface UserAssertedStmNote {
  readonly version: typeof USER_ASSERTED_STM_NOTE_VERSION;
  readonly owner_account_id: string;
  readonly note_id: string;
  readonly formation_work_id: string;
  readonly write_id: string;
  readonly content: string;
  readonly metadata: Readonly<UserAssertedStmNoteMetadata>;
  readonly content_digest: string;
  readonly note_digest: string;
}

export interface SealUserAssertedStmNoteInput {
  readonly owner_account_id: string;
  readonly write_id: string;
  readonly content: string;
  readonly metadata: Readonly<UserAssertedStmNoteMetadata>;
}

const TOKEN = /^[\x21-\x7e]{1,256}$/;
const TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,3})?Z$/;
const DIGEST = /^[a-f0-9]{64}$/;
const WRITE_DOORS = new Set<StmNoteWriteDoor>(["http", "mcp", "mcp_legacy"]);
const MAX_CONTENT_CODE_POINTS = 65_536;

const fail = (code: string): never => { throw new TypeError(`user asserted stm note ${code}`); };

const token = (value: unknown, code: string): string => {
  if (typeof value !== "string" || !TOKEN.test(value)) fail(code);
  return value;
};

const timestamp = (value: unknown, code: string): string => {
  const parsed = token(value, code);
  if (!TIMESTAMP.test(parsed) || Number.isNaN(Date.parse(parsed))) fail(code);
  return parsed;
};

const boundedContent = (value: unknown, code: string): string => {
  if (typeof value !== "string" || value.length === 0 || value !== value.trim()
    || [...value].length > MAX_CONTENT_CODE_POINTS || /[\p{Cc}\p{Cs}]/u.test(value)) fail(code);
  return value;
};

const exactRecord = (value: unknown, keys: readonly string[], code: string): Record<string, unknown> => {
  if (value === null || typeof value !== "object" || Array.isArray(value) || isProxy(value)
    || Object.getPrototypeOf(value) !== Object.prototype) fail(code);
  const ownKeys = Reflect.ownKeys(value as object);
  if (ownKeys.length !== keys.length || ownKeys.some((key) => typeof key !== "string" || !keys.includes(key))) {
    fail(code);
  }
  for (const key of keys) {
    const descriptor = Object.getOwnPropertyDescriptor(value, key);
    if (!descriptor || !("value" in descriptor) || !descriptor.enumerable) fail(code);
  }
  return value as Record<string, unknown>;
};

export const stmNoteFormationWorkId = (
  ownerAccountId: string,
  writeId: string,
): string => `formation:stm-note:${sha256CanonicalContent({
  contract_version: USER_ASSERTED_STM_NOTE_VERSION,
  owner_account_id: ownerAccountId,
  write_id: writeId,
})}`;

export const stmNoteId = (
  ownerAccountId: string,
  writeId: string,
): string => `stm-note:${sha256CanonicalContent({
  contract_version: USER_ASSERTED_STM_NOTE_VERSION,
  owner_account_id: ownerAccountId,
  write_id: writeId,
})}`;

const metadataFields = (value: unknown): UserAssertedStmNoteMetadata => {
  const input = exactRecord(value, ["write_door", "client_write_ref", "submitted_at"], "invalid_metadata");
  const writeDoor = input["write_door"];
  if (typeof writeDoor !== "string" || !WRITE_DOORS.has(writeDoor as StmNoteWriteDoor)) fail("invalid_metadata");
  const clientWriteRef = input["client_write_ref"];
  if (clientWriteRef !== null && (typeof clientWriteRef !== "string" || !TOKEN.test(clientWriteRef))) {
    fail("invalid_metadata");
  }
  return Object.freeze({
    write_door: writeDoor as StmNoteWriteDoor,
    client_write_ref: clientWriteRef as string | null,
    submitted_at: timestamp(input["submitted_at"], "invalid_metadata"),
  });
};

export const sealUserAssertedStmNote = (
  inputValue: SealUserAssertedStmNoteInput,
): Readonly<UserAssertedStmNote> => {
  const input = exactRecord(inputValue, ["owner_account_id", "write_id", "content", "metadata"], "invalid_input");
  const owner = token(input["owner_account_id"], "invalid_input");
  const writeId = token(input["write_id"], "invalid_input");
  const content = boundedContent(input["content"], "invalid_input");
  const metadata = metadataFields(input["metadata"]);
  const contentDigest = sha256CanonicalContent({
    contract_version: USER_ASSERTED_STM_NOTE_VERSION,
    content,
  });
  const withoutDigests = {
    version: USER_ASSERTED_STM_NOTE_VERSION,
    owner_account_id: owner,
    note_id: stmNoteId(owner, writeId),
    formation_work_id: stmNoteFormationWorkId(owner, writeId),
    write_id: writeId,
    content,
    metadata,
  };
  const noteDigest = sha256CanonicalContent({
    contract_version: USER_ASSERTED_STM_NOTE_VERSION,
    ...withoutDigests,
    content_digest: contentDigest,
  });
  return Object.freeze({
    ...withoutDigests,
    content_digest: contentDigest,
    note_digest: noteDigest,
  });
};

export const parseUserAssertedStmNote = (value: unknown): Readonly<UserAssertedStmNote> => {
  const input = exactRecord(value, [
    "version", "owner_account_id", "note_id", "formation_work_id", "write_id",
    "content", "metadata", "content_digest", "note_digest",
  ], "invalid_note");
  if (input["version"] !== USER_ASSERTED_STM_NOTE_VERSION) fail("invalid_note");
  const reconstructed = sealUserAssertedStmNote({
    owner_account_id: token(input["owner_account_id"], "invalid_note"),
    write_id: token(input["write_id"], "invalid_note"),
    content: boundedContent(input["content"], "invalid_note"),
    metadata: metadataFields(input["metadata"]),
  });
  const contentDigest = token(input["content_digest"], "invalid_note");
  const noteDigest = token(input["note_digest"], "invalid_note");
  if (!DIGEST.test(contentDigest) || !DIGEST.test(noteDigest)) fail("invalid_note");
  if (reconstructed.note_id !== input["note_id"]
    || reconstructed.formation_work_id !== input["formation_work_id"]
    || reconstructed.content_digest !== contentDigest
    || reconstructed.note_digest !== noteDigest) fail("note_digest_mismatch");
  return reconstructed;
};
