export interface LegacyPermissionOption {
  kind: string;
  optionId: string;
}

export interface LegacyPermissionDecision {
  optionId: string;
  optionKind: string;
  acpResult: {
    outcome: {
      outcome: "selected";
      optionId: string;
    };
  };
  auditEvent: {
    type: "approval.resolved";
    policy: "legacy_high_trust";
    adapterId: "acp";
    requestId?: number | string;
    optionId: string;
    optionKind: string;
    automatic: true;
  };
}

export class LegacyPermissionPolicy {
  resolveAcpPermission(input: {
    requestId?: number | string;
    options: LegacyPermissionOption[];
  }): LegacyPermissionDecision {
    const selected =
      input.options.find((option) => option.kind === "allow_always") ??
      input.options.find((option) => option.kind === "allow_once") ??
      input.options[0] ??
      { kind: "legacy_fallback", optionId: "allow" };

    return {
      optionId: selected.optionId,
      optionKind: selected.kind,
      acpResult: {
        outcome: {
          outcome: "selected",
          optionId: selected.optionId,
        },
      },
      auditEvent: {
        type: "approval.resolved",
        policy: "legacy_high_trust",
        adapterId: "acp",
        requestId: input.requestId,
        optionId: selected.optionId,
        optionKind: selected.kind,
        automatic: true,
      },
    };
  }
}

export const legacyPermissionPolicy = new LegacyPermissionPolicy();
