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
    policy: "legacy_high_trust" | "external_constrained";
    adapterId: string;
    requestId?: number | string;
    optionId: string;
    optionKind: string;
    automatic: true;
  };
}

export interface LegacyPermissionRejection {
  acpError: {
    code: number;
    message: string;
  };
  auditEvent: {
    type: "approval.rejected";
    policy: "external_constrained";
    adapterId: string;
    requestId?: number | string;
    automatic: true;
    reason: string;
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

  resolveExternalAcpPermission(input: {
    adapterId: string;
    requestId?: number | string;
    options: LegacyPermissionOption[];
  }): LegacyPermissionDecision | LegacyPermissionRejection {
    const selected =
      input.options.find((option) => /deny|reject|disallow/i.test(option.kind)) ??
      input.options.find((option) => option.kind === "allow_once") ??
      input.options.find((option) => option.kind !== "allow_always");

    if (!selected) {
      return {
        acpError: {
          code: -32001,
          message: "External adapter permission requires explicit user approval",
        },
        auditEvent: {
          type: "approval.rejected",
          policy: "external_constrained",
          adapterId: input.adapterId,
          requestId: input.requestId,
          automatic: true,
          reason: "no_non_permanent_option",
        },
      };
    }

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
        policy: "external_constrained",
        adapterId: input.adapterId,
        requestId: input.requestId,
        optionId: selected.optionId,
        optionKind: selected.kind,
        automatic: true,
      },
    };
  }
}

export const legacyPermissionPolicy = new LegacyPermissionPolicy();
