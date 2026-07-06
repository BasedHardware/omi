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

  it("auto-approves autonomous external adapters (hermes/openclaw) even when a deny option is offered", () => {
    const policy = new LegacyPermissionPolicy();

    // Real-world tool-call options include a reject variant; autonomous adapters
    // must still pick the allow option (never the deny) so their tools execute.
    for (const adapterId of ["hermes", "openclaw"]) {
      const decision = policy.resolveExternalAcpPermission({
        adapterId,
        requestId: 7,
        options: [
          { kind: "allow_once", optionId: "once" },
          { kind: "reject_once", optionId: "deny" },
        ],
      });
      expect("acpResult" in decision ? decision.acpResult.outcome.optionId : "").toBe("once");
      expect(decision.auditEvent).toMatchObject({
        type: "approval.resolved",
        policy: "external_autonomous",
        adapterId,
        requestId: 7,
        optionId: "once",
        automatic: true,
      });
    }
  });

  it("keeps unknown external ACP adapters on the conservative constrained path", () => {
    const policy = new LegacyPermissionPolicy();

    // A deny option is taken when present.
    const denied = policy.resolveExternalAcpPermission({
      adapterId: "someexternal",
      options: [
        { kind: "allow_once", optionId: "once" },
        { kind: "reject_once", optionId: "deny" },
      ],
    });
    expect("acpResult" in denied ? denied.acpResult.outcome.optionId : "").toBe("deny");
    expect(denied.auditEvent).toMatchObject({ policy: "external_constrained" });

    // Only a permanent-allow option => explicit rejection (no permanent auto-grant).
    const rejected = policy.resolveExternalAcpPermission({
      adapterId: "someexternal",
      requestId: 9,
      options: [{ kind: "allow_always", optionId: "always" }],
    });
    expect("acpError" in rejected ? rejected.acpError.code : 0).toBe(-32001);
    expect(rejected.auditEvent).toMatchObject({
      policy: "external_constrained",
      adapterId: "someexternal",
      requestId: 9,
    });
  });
});
