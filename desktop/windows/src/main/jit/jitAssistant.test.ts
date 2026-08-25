import { describe, expect, it } from 'vitest'
import { jitDeliveryTelemetry } from './jitTelemetry'

describe('JIT delivery telemetry', () => {
  it('omits the ambient trigger handle so app/window context cannot escape analytics', () => {
    const payload = jitDeliveryTelemetry('ambient', 'ambient:opaque-handle')
    expect(payload).toEqual({ lane: 'ambient' })
    expect(JSON.stringify(payload)).not.toContain('opaque-handle')
  })

  it('keeps the planned trigger handle for server-correlated delivery receipts', () => {
    expect(jitDeliveryTelemetry('planned', 'trigger-opaque-id')).toEqual({
      lane: 'planned',
      triggerId: 'trigger-opaque-id'
    })
  })
})
