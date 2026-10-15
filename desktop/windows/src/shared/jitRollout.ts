export type JitTriState = 'enabled' | 'disabled' | 'unknown'

export type JitRolloutDecision = {
  rollout: JitTriState
  killSwitch: JitTriState
  effective: JitTriState
  reason: string
  errorClass: string
}
