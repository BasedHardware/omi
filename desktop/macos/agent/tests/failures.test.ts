import { describe, expect, it } from "vitest";

import { AdapterRuntimeError, unexpectedQueryErrorDiagnostic } from "../src/runtime/failures.js";

describe("query error diagnostics", () => {
  it("does not label the exact recoverable context-admission mismatch as unhandled", () => {
    expect(unexpectedQueryErrorDiagnostic(
      new Error("context_snapshot_projection_mismatch"),
    )).toBeNull();
    expect(unexpectedQueryErrorDiagnostic(new AdapterRuntimeError({
      code: "runtime_query_failed",
      source: "runtime",
      retryable: false,
      userMessage: "context_snapshot_projection_mismatch",
    }))).toBeNull();
  });

  it("preserves unexpected query error logging and rejects decorated near-matches", () => {
    expect(unexpectedQueryErrorDiagnostic(new Error("adapter exploded")))
      .toBe("Unhandled query error: Error: adapter exploded");
    expect(unexpectedQueryErrorDiagnostic(
      new Error("prefix context_snapshot_projection_mismatch suffix"),
    )).toBe("Unhandled query error: Error: prefix context_snapshot_projection_mismatch suffix");
  });
});
