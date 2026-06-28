import { describe, expect, it } from "vitest";
import { LegacyPermissionPolicy } from "../src/legacy-permission-policy.js";

describe("LegacyPermissionPolicy", () => {
  it("preserves ACP high-trust auto approval preference order", () => {
    const policy = new LegacyPermissionPolicy();
    const decision = policy.resolveAcpPermission({
      requestId: 42,
      options: [
        { kind: "allow_once", optionId: "once" },
        { kind: "allow_always", optionId: "always" },
      ],
    });

    expect(decision.acpResult).toEqual({
      outcome: { outcome: "selected", optionId: "always" },
    });
    expect(decision.auditEvent).toMatchObject({
      type: "approval.resolved",
      policy: "legacy_high_trust",
      adapterId: "acp",
      requestId: 42,
      optionId: "always",
      automatic: true,
    });
  });

  it("falls back to allow_once, then legacy allow", () => {
    const policy = new LegacyPermissionPolicy();

    expect(policy.resolveAcpPermission({
      options: [{ kind: "allow_once", optionId: "once" }],
    }).optionId).toBe("once");

    expect(policy.resolveAcpPermission({ options: [] }).optionId).toBe("allow");
  });

  it("keeps external ACP adapters off permanent auto-approval", () => {
    const policy = new LegacyPermissionPolicy();

    const once = policy.resolveExternalAcpPermission({
      adapterId: "hermes",
      options: [
        { kind: "allow_always", optionId: "always" },
        { kind: "allow_once", optionId: "once" },
      ],
    });
    expect("acpResult" in once ? once.acpResult.outcome.optionId : "").toBe("once");

    const rejected = policy.resolveExternalAcpPermission({
      adapterId: "openclaw",
      requestId: 9,
      options: [{ kind: "allow_always", optionId: "always" }],
    });
    expect("acpError" in rejected ? rejected.acpError.code : 0).toBe(-32001);
    expect(rejected.auditEvent).toMatchObject({
      policy: "external_constrained",
      adapterId: "openclaw",
      requestId: 9,
    });
  });
});
