/** Analytics for ambient JIT is deliberately content-free. The app/window
 * context is useful to the local matcher and agent prompt, but it must never
 * become a retained trigger identifier or cross-process event payload. */
export function jitDeliveryTelemetry(
  lane: 'planned' | 'ambient',
  triggerId: string
): { lane: 'planned' | 'ambient'; triggerId?: string } {
  return lane === 'planned' ? { lane, triggerId } : { lane }
}
