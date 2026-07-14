import { Mic } from 'lucide-react'
import { PermissionStep } from './PermissionStep'
import { setPreferences } from '../../lib/preferences'

type MicPermissionStepProps = {
  stepIndex: number
  totalSteps: number
  aside?: React.ReactNode
  onContinue: () => void
  onSkip?: () => void
}

/**
 * Read the real Windows microphone permission without prompting, so a mic the user
 * already allowed shows as allowed (and one they allow in Windows Settings mid-step is
 * picked up on the next poll / on refocus).
 *
 * This asks MAIN, which reads the Capability Access Manager registry. It deliberately
 * does NOT use `navigator.permissions.query({name:'microphone'})`: Electron registers no
 * permission-check handler, so Chromium answers 'granted' unconditionally — including on
 * a fresh profile with the mic blocked by Windows. Trusting it made this step
 * false-grant and skip itself on every run, without ever asking the OS.
 *
 * Unknown/unreadable reads as not-granted: never assume a grant we can't see.
 */
async function isMicGranted(): Promise<boolean> {
  try {
    return (await window.omi?.getMicPermissionState?.()) === 'granted'
  } catch {
    return false
  }
}

export function MicPermissionStep({
  stepIndex,
  totalSteps,
  aside,
  onContinue,
  onSkip
}: MicPermissionStepProps): React.JSX.Element {
  // Trigger the real Windows microphone grant. getUserMedia surfaces the OS
  // prompt; we immediately release the device since we only needed the grant.
  // A denial REJECTS — PermissionStep turns that into an explicit denied state
  // (never "Granted", never an auto-advance).
  const requestAccess = async (): Promise<void> => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      stream.getTracks().forEach((t) => t.stop())
    } catch (e) {
      const err = e as Error
      throw new Error(
        err.name === 'NotAllowedError'
          ? 'Windows blocked microphone access. Open Settings → Privacy & security → Microphone, allow this app, then come back — Omi will pick it up automatically.'
          : `Microphone access failed: ${err.message}`
      )
    }
  }

  // Granting the mic opts into always-on listening — continuous recording is on
  // from here (the background host starts streaming once onboarding completes).
  // One step, no separate continuous-recording screen; toggle it off anytime via
  // the sidebar mic switch or Settings.
  //
  // PermissionStep only calls this when the user AFFIRMATIVELY takes the permission —
  // their own grant click, or Continue on a mic we found already allowed. It is never
  // called off a bare detection or a Skip, so always-on mic streaming can no longer be
  // switched on by a grant that never happened.
  const handleGranted = (): void => {
    setPreferences({ continuousRecording: true })
  }

  return (
    <PermissionStep
      stepIndex={stepIndex}
      totalSteps={totalSteps}
      aside={aside}
      eyebrow="PERMISSION"
      title="Let Omi use your mic"
      subtitle="This lets Omi transcribe meetings and voice notes"
      icon={<Mic className="h-5 w-5 text-white/60" />}
      cardLabel="Microphone"
      statusText={{
        idle: 'Not granted yet',
        waiting: 'Waiting for Windows',
        granted: 'Granted',
        denied: 'Blocked by Windows'
      }}
      buttonLabel={{
        idle: 'Grant access',
        waiting: 'Waiting for Windows',
        granted: 'Granted',
        denied: 'Try again'
      }}
      onActivate={requestAccess}
      checkGranted={isMicGranted}
      onGranted={handleGranted}
      recoveryLabel="Open Windows Settings"
      onRecover={() => window.omi?.openMicPrivacySettings?.()}
      onContinue={onContinue}
      onSkip={onSkip}
    />
  )
}
