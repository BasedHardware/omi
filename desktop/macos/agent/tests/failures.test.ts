import { describe, expect, it } from "vitest";

import {
  AdapterRuntimeError,
  attachWorkerRecycle,
  failureFromError,
  isProviderBillingFailure,
  unexpectedQueryErrorDiagnostic,
  WORKER_RECYCLED_NEXT_SEND_MESSAGE,
} from "../src/runtime/failures.js";

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

describe("provider billing vs worker recycle", () => {
  it("matches both HTTP-first and status-first 402 phrasings", () => {
    for (const text of [
      "HTTP 402 status code (no body)",
      "Request failed: http/402",
      "402 status from provider",
      "status 402",
      "status code: 402",
      "status code = 402",
    ]) {
      expect(isProviderBillingFailure(text), text).toBe(true);
    }
    expect(isProviderBillingFailure("used 402 tokens")).toBe(false);
  });

  it("marks a bare HTTP 402 as non-retryable quota before recycle wrapping", () => {
    const failure = failureFromError(new Error("HTTP 402 status code (no body)"), {
      code: "adapter_execution_failed",
      source: "adapter_execution",
      adapterId: "pi-mono",
      retryable: true,
    });
    expect(failure).toMatchObject({
      failureCode: "quota_exceeded",
      retryable: false,
      technicalMessage: "HTTP 402 status code (no body)",
    });
    expect(attachWorkerRecycle(failure, {
      stopSucceeded: true,
      bindingInvalidationSucceeded: true,
    })).toMatchObject({
      userMessage: "HTTP 402 status code (no body)",
      retryable: false,
      recoveryAction: "worker_recycled",
      recoveryOutcome: "recovered",
    });
    expect(attachWorkerRecycle(failure, {
      stopSucceeded: true,
      bindingInvalidationSucceeded: true,
    }).userMessage).not.toBe(WORKER_RECYCLED_NEXT_SEND_MESSAGE);
  });

  it("still invites a next send when the recycled worker was actually poisoned", () => {
    const failure = failureFromError(new Error("poisoned local adapter state"), {
      code: "adapter_execution_failed",
      source: "adapter_execution",
      adapterId: "pi-mono",
      retryable: true,
    });
    expect(attachWorkerRecycle(failure, {
      stopSucceeded: true,
      bindingInvalidationSucceeded: true,
    })).toMatchObject({
      userMessage: WORKER_RECYCLED_NEXT_SEND_MESSAGE,
      retryable: true,
      retryDisposition: "next_send",
      recoveryAction: "worker_recycled",
    });
  });
});
