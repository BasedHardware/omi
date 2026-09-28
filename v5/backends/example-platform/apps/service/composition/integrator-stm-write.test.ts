import { describe, expect, test } from "bun:test";

import {
  INTEGRATOR_STM_WRITE_VERSION,
  STM_NOTE_DELETE_CORRECTION_CONTENT,
  materializeIntegratorStmWrite,
} from "./integrator-stm-write";

describe("integrator STM write composition", () => {
  test("maps create, edit, and delete onto notes plus append-only correction", () => {
    const created = materializeIntegratorStmWrite({
      operation: "create",
      owner_account_id: "account:alice",
      write_id: "write:one",
      content: "Remember the Atlas launch.",
      write_door: "mcp",
      client_write_ref: "client:one",
      submitted_at: "2026-08-14T00:00:00Z",
    });
    expect(created.version).toBe(INTEGRATOR_STM_WRITE_VERSION);
    expect(created.operation).toBe("create");
    expect(created.previous_write_id).toBeNull();
    expect(created.note.write_id).toBe("write:one");
    expect(created.note.content).toBe("Remember the Atlas launch.");

    const edited = materializeIntegratorStmWrite({
      operation: "edit",
      owner_account_id: "account:alice",
      write_id: "write:ignored",
      content: "Remember the delayed Atlas launch.",
      write_door: "mcp_legacy",
      client_write_ref: "client:one",
      submitted_at: "2026-08-14T00:01:00Z",
    }, created.note.write_id);
    expect(edited.operation).toBe("edit");
    expect(edited.previous_write_id).toBe("write:one");
    expect(edited.note.write_id).not.toBe("write:one");
    expect(edited.note.write_id.startsWith("edit:")).toBe(true);
    expect(edited.note.content).toBe("Remember the delayed Atlas launch.");

    const deleted = materializeIntegratorStmWrite({
      operation: "delete",
      owner_account_id: "account:alice",
      write_id: "write:ignored",
      content: "should be replaced",
      write_door: "http",
      client_write_ref: null,
      submitted_at: "2026-08-14T00:02:00Z",
    }, edited.note.write_id);
    expect(deleted.operation).toBe("delete");
    expect(deleted.note.content).toBe(STM_NOTE_DELETE_CORRECTION_CONTENT);
    expect(deleted.note.write_id.startsWith("delete:")).toBe(true);
    expect(deleted.note.note_id).not.toBe(created.note.note_id);
  });
});
