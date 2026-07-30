// Pure helper for resuming the onboarding wizard. The current step index is
// persisted in preferences (`onboardingStep`) so quitting mid-onboarding resumes
// where the user left off. The step list can change between app versions, so a
// saved index is clamped into range on read. No DOM/Electron deps — unit-tested.

/**
 * Resolve the step to resume at from a persisted value. Non-numbers (undefined,
 * NaN, from an older/newer schema) resolve to 0; negatives clamp to 0; anything
 * past the last step clamps to the last step. Fractional values floor.
 */
export function clampOnboardingStep(saved: unknown, totalSteps: number): number {
  const lastStep = Math.max(0, totalSteps - 1)
  if (typeof saved !== 'number' || !Number.isFinite(saved)) return 0
  const floored = Math.floor(saved)
  if (floored < 0) return 0
  if (floored > lastStep) return lastStep
  return floored
}
