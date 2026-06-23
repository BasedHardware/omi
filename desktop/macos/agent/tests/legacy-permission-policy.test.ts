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
});
