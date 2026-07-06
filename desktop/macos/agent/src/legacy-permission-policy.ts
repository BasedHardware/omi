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
    policy: "legacy_high_trust" | "external_constrained" | "external_autonomous";
    adapterId: string;
    requestId?: number | string;
    optionId: string;
    optionKind: string;
    automatic: true;
  };
}

/**
 * External ACP adapters whose underlying agent is trusted to run its own tools
 * autonomously (terminal, file edits) the same way OpenClaw already does.
 *
 * OpenClaw's backend self-authorizes tool calls inside its own subprocess and
 * never sends `session/request_permission` to us — so its tools always execute
 * and the `external_constrained` deny path is never reached. Hermes, by
 * contrast, follows the ACP permission handshake strictly and asks us before
 * every tool call, so under `external_constrained` (which prefers a deny/reject
 * option) it gets auto-denied and can never act.
 *
 * Listing both here gives Hermes the same effective autonomy OpenClaw has: when
 * one of these adapters does request permission, we auto-approve it rather than
 * deny. `openclaw` is included for parity/future-proofing (a no-op today since
 * it never asks). Any other/unknown external adapter stays on the conservative
 * `external_constrained` path and is not affected.
 */
export const AUTONOMOUS_EXTERNAL_ADAPTERS: ReadonlySet<string> = new Set(["hermes", "openclaw"]);

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
    // Adapters trusted to run tools autonomously (see AUTONOMOUS_EXTERNAL_ADAPTERS)
    // get the same effective auto-approval OpenClaw already enjoys: prefer an
    // allow option, and never fall through to a deny/reject.
    if (AUTONOMOUS_EXTERNAL_ADAPTERS.has(input.adapterId)) {
      const allow =
        input.options.find((option) => option.kind === "allow_once") ??
        input.options.find((option) => option.kind === "allow_always") ??
        input.options.find((option) => !/deny|reject|disallow/i.test(option.kind)) ??
        input.options[0] ??
        { kind: "legacy_fallback", optionId: "allow" };

      return {
        optionId: allow.optionId,
        optionKind: allow.kind,
        acpResult: {
          outcome: {
            outcome: "selected",
            optionId: allow.optionId,
          },
        },
        auditEvent: {
          type: "approval.resolved",
          policy: "external_autonomous",
          adapterId: input.adapterId,
          requestId: input.requestId,
          optionId: allow.optionId,
          optionKind: allow.kind,
          automatic: true,
        },
      };
    }

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
