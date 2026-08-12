import { trackOnboardingStepCompleted, type WindowsOnboardingStep } from './analytics'

/** One emission per rendered step visit, even when a delayed click races. */
export function createOnboardingStepRecorder(): {
  beginStep: (step: number) => void
  record: (step: number, stepName: WindowsOnboardingStep, skipped: boolean) => boolean
} {
  let activeStep: number | null = null
  let completed = false
  return {
    beginStep(step): void {
      activeStep = step
      completed = false
    },
    record(step, stepName, skipped): boolean {
      if (activeStep !== step) {
        activeStep = step
        completed = false
      }
      if (completed) return false
      completed = true
      trackOnboardingStepCompleted(step, stepName, skipped)
      return true
    }
  }
}
