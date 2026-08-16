// Minimal ACP permission auto-resolver — the behavior of macOS's
// resolveAcpPermission / resolveExternalAcpPermission without the surrounding
// tool-bundle/capability-grant policy engine (which is coupled to the macOS
// kernel and has no Windows equivalent). This is a deliberate, permanent
// simplification for the headless adapter core: Claude Code (first-party
// bundled bridge) auto-approves so a voice-triggered task never stalls on an
// invisible prompt; external adapters never receive a permanent "allow_always"
// grant automatically. A real user-facing approval UI belongs to the routing/
// settings layers (see the win-agents PR train), not this module.

export interface AcpPermissionOption {
  kind: string
  optionId: string
}

export interface AcpPermissionAuditEvent {
  type: 'approval.resolved' | 'approval.rejected'
  policy: 'desktop_high_trust' | 'external_constrained'
  adapterId: string
  requestId?: number | string
  optionId?: string
  optionKind?: string
  automatic: true
  reason?: string
}

export interface AcpPermissionDecision {
  optionId: string
  optionKind: string
  acpResult: { outcome: { outcome: 'selected'; optionId: string } }
  auditEvent: AcpPermissionAuditEvent
}

export interface AcpPermissionRejection {
  acpError: { code: number; message: string }
  auditEvent: AcpPermissionAuditEvent
}

/** Claude Code: trusted first-party bridge — auto-approve, preferring the widest grant. */
export function resolveAcpPermission(input: {
  requestId?: number | string
  options: AcpPermissionOption[]
}): AcpPermissionDecision {
  const selected = input.options.find((option) => option.kind === 'allow_always') ??
    input.options.find((option) => option.kind === 'allow_once') ??
    input.options[0] ?? { kind: 'fallback', optionId: 'allow' }

  return {
    optionId: selected.optionId,
    optionKind: selected.kind,
    acpResult: {
      outcome: {
        outcome: 'selected',
        optionId: selected.optionId
      }
    },
    auditEvent: {
      type: 'approval.resolved',
      policy: 'desktop_high_trust',
      adapterId: 'acp',
      requestId: input.requestId,
      optionId: selected.optionId,
      optionKind: selected.kind,
      automatic: true
    }
  }
}

/**
 * External adapters (OpenClaw/Hermes/Codex): never auto-grant a permanent
 * "allow_always" to a user-installed third-party binary. Prefer a one-shot
 * allow, else an explicit deny option, else reject the request outright
 * (ACP error -32001) so the adapter surfaces it instead of silently escalating.
 */
export function resolveExternalAcpPermission(input: {
  adapterId: string
  requestId?: number | string
  options: AcpPermissionOption[]
}): AcpPermissionDecision | AcpPermissionRejection {
  const selected =
    input.options.find((option) => option.kind === 'allow_once') ??
    input.options.find((option) => /deny|reject|disallow/i.test(option.kind)) ??
    input.options.find((option) => option.kind !== 'allow_always')

  if (!selected) {
    return {
      acpError: {
        code: -32001,
        message: 'External adapter permission requires explicit user approval'
      },
      auditEvent: {
        type: 'approval.rejected',
        policy: 'external_constrained',
        adapterId: input.adapterId,
        requestId: input.requestId,
        automatic: true,
        reason: 'no_non_permanent_option'
      }
    }
  }

  return {
    optionId: selected.optionId,
    optionKind: selected.kind,
    acpResult: {
      outcome: {
        outcome: 'selected',
        optionId: selected.optionId
      }
    },
    auditEvent: {
      type: 'approval.resolved',
      policy: 'external_constrained',
      adapterId: input.adapterId,
      requestId: input.requestId,
      optionId: selected.optionId,
      optionKind: selected.kind,
      automatic: true
    }
  }
}
