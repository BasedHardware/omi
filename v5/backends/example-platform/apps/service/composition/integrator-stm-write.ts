import { isProxy } from "node:util/types";

import {
  sealUserAssertedStmNote,
  type StmNoteWriteDoor,
  type UserAssertedStmNote,
} from "../../../core/stm/note";
import { sha256CanonicalContent } from "../../../core/retrieve/content-digest";
import {
  defineStmNoteIngestion,
  type StmNoteFormationIngestionPort,
  type StmNoteFormationIngestionRequest,
} from "../stm/stm-note-ingestion";
import type { AuthorizedLedgerWriteContext } from "../auth/authorized-context";

export const INTEGRATOR_STM_WRITE_VERSION = "integrator-stm-write-v1" as const;
export const STM_NOTE_DELETE_CORRECTION_CONTENT = "stm-note-correction:delete" as const;

export type IntegratorStmWriteOperation = "create" | "edit" | "delete";

export interface IntegratorStmWriteInput {
  readonly operation: IntegratorStmWriteOperation;
  readonly owner_account_id: string;
  readonly write_id: string;
  readonly content: string;
  readonly write_door: StmNoteWriteDoor;
  readonly client_write_ref: string | null;
  readonly submitted_at: string;
}

export interface IntegratorStmWriteNote {
  readonly version: typeof INTEGRATOR_STM_WRITE_VERSION;
  readonly operation: IntegratorStmWriteOperation;
  readonly previous_write_id: string | null;
  readonly note: UserAssertedStmNote;
}

const OPERATIONS = new Set<IntegratorStmWriteOperation>(["create", "edit", "delete"]);
const fail = (code: string): never => { throw new TypeError(`integrator stm write ${code}`); };

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

export const materializeIntegratorStmWrite = (
  inputValue: IntegratorStmWriteInput,
  previousWriteId: string | null = null,
): Readonly<IntegratorStmWriteNote> => {
  const input = exactRecord(inputValue, [
    "operation", "owner_account_id", "write_id", "content",
    "write_door", "client_write_ref", "submitted_at",
  ], "invalid_input");
  const operation = input["operation"];
  if (typeof operation !== "string" || !OPERATIONS.has(operation as IntegratorStmWriteOperation)) {
    fail("invalid_operation");
  }
  if (operation === "create" && previousWriteId !== null) fail("create_has_previous");
  if ((operation === "edit" || operation === "delete") && previousWriteId === null) {
    fail("missing_previous_write");
  }
  const content = operation === "delete"
    ? STM_NOTE_DELETE_CORRECTION_CONTENT
    : input["content"];
  const writeId = operation === "edit"
    ? `edit:${sha256CanonicalContent({
        contract_version: INTEGRATOR_STM_WRITE_VERSION,
        previous_write_id: previousWriteId,
        content,
      })}`
    : operation === "delete"
      ? `delete:${sha256CanonicalContent({
          contract_version: INTEGRATOR_STM_WRITE_VERSION,
          previous_write_id: previousWriteId,
        })}`
      : input["write_id"];
  const note = sealUserAssertedStmNote({
    owner_account_id: input["owner_account_id"] as string,
    write_id: writeId as string,
    content: content as string,
    metadata: {
      write_door: input["write_door"] as StmNoteWriteDoor,
      client_write_ref: input["client_write_ref"] as string | null,
      submitted_at: input["submitted_at"] as string,
    },
  });
  return Object.freeze({
    version: INTEGRATOR_STM_WRITE_VERSION,
    operation: operation as IntegratorStmWriteOperation,
    previous_write_id: previousWriteId,
    note,
  });
};

export const composeIntegratorStmWrite = (
  formation: Parameters<typeof defineStmNoteIngestion>[0],
): {
  ingest(
    context: AuthorizedLedgerWriteContext,
    write: IntegratorStmWriteNote,
    rest: Omit<StmNoteFormationIngestionRequest, "note">,
  ): ReturnType<StmNoteFormationIngestionPort["accept"]>;
} => {
  const ingestion = defineStmNoteIngestion(formation);
  return Object.freeze({
    ingest(context, write, rest) {
      if (write.version !== INTEGRATOR_STM_WRITE_VERSION) fail("invalid_write");
      return ingestion.accept(context, { ...rest, note: write.note });
    },
  });
};
