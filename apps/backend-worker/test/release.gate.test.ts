import { describe, expect, test } from "bun:test";

import { parseReleaseGateArgs } from "../scripts/verify-release";

describe("parseReleaseGateArgs", () => {
  test("accepts a native Workers Observability release gate", () => {
    expect(
      parseReleaseGateArgs([
        "https://worker.example.invalid/ready",
        "--environment",
        "staging",
        "--observability-sink-mode",
        "cloudflare_only",
      ])
    ).toEqual({
      kind: "ok",
      value: {
        readyUrl: "https://worker.example.invalid/ready",
        environment: "staging",
        sinkMode: "cloudflare_only",
      },
    });
  });

  test("requires opaque operator evidence before allowing Better Stack mode", () => {
    expect(
      parseReleaseGateArgs([
        "https://worker.example.invalid/ready",
        "--environment",
        "staging",
        "--observability-sink-mode",
        "better_stack",
      ])
    ).toEqual({ kind: "error", reason: "better_stack_evidence_required" });

    expect(
      parseReleaseGateArgs([
        "https://worker.example.invalid/ready",
        "--environment",
        "staging",
        "--observability-sink-mode",
        "better_stack",
        "--better-stack-evidence",
        "ops-20260818-1",
      ])
    ).toEqual({
      kind: "ok",
      value: {
        readyUrl: "https://worker.example.invalid/ready",
        environment: "staging",
        sinkMode: "better_stack",
        betterStackEvidence: "ops-20260818-1",
      },
    });
  });

  test("rejects evidence that could be a credential and duplicate options", () => {
    expect(
      parseReleaseGateArgs([
        "https://worker.example.invalid/ready",
        "--environment",
        "staging",
        "--observability-sink-mode",
        "better_stack",
        "--better-stack-evidence",
        "contains space",
      ])
    ).toEqual({ kind: "error", reason: "invalid_better_stack_evidence" });

    expect(
      parseReleaseGateArgs([
        "https://worker.example.invalid/ready",
        "--environment",
        "staging",
        "--environment",
        "production",
        "--observability-sink-mode",
        "cloudflare_only",
      ])
    ).toEqual({ kind: "error", reason: "duplicate_option" });
  });
});
