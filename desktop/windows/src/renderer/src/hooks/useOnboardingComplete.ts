import { useEffect, useState } from 'react'
import { isOnboardingComplete, onPreferencesChange } from '../lib/preferences'

// Reactive view of the local onboarding flag so App re-renders (and re-routes)
// the moment the wizard finishes.
export function useOnboardingComplete(): boolean {
  const [complete, setComplete] = useState(isOnboardingComplete())

  useEffect(() => {
    return onPreferencesChange(() => setComplete(isOnboardingComplete()))
  }, [])

  return complete
}
