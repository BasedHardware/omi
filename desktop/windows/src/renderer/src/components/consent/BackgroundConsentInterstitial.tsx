import { useState } from 'react'
import { getPreferences, setPreferences } from '../../lib/preferences'
import { shouldShowBackgroundConsent } from '../../lib/backgroundConsent'
import { BackgroundConsentControls } from './BackgroundConsentControls'

/**
 * One-time modal shown to existing users on the first launch after Omi becomes a
 * tray-resident, launch-at-login companion. Nothing is silently switched on:
 * launch-at-login starts unchecked (explicit opt-in), and the user's existing
 * continuous-listening choice is preserved and shown. Acknowledging stamps
 * backgroundConsentAt so it never reappears. New users don't see this — they
 * consent inline during onboarding (see shouldShowBackgroundConsent).
 */
export function BackgroundConsentInterstitial(): React.JSX.Element | null {
  const [open, setOpen] = useState(() => shouldShowBackgroundConsent(getPreferences()))
  const [listening, setListening] = useState(() => !!getPreferences().continuousRecording)
  const [launchAtLogin, setLaunchAtLogin] = useState(false)

  if (!open) return null

  const acknowledge = (): void => {
    setPreferences({
      continuousRecording: listening,
      backgroundConsentAt: Date.now(),
      ...(listening ? { recordingConsentedAt: Date.now() } : {})
    })
    void window.omi?.setLaunchAtLogin?.(launchAtLogin)
    setOpen(false)
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-bg-primary/50 p-6 backdrop-blur-md">
      <div className="glass w-full max-w-[480px] p-7">
        <h2 className="font-display text-2xl font-semibold text-white/95">
          Omi now runs in the background
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-white/60">
          Omi keeps working from your system tray so it’s always ready. Take a moment to confirm how
          it should behave — you can change any of this later in Settings.
        </p>
        <div className="mt-6">
          <BackgroundConsentControls
            listening={listening}
            onListeningChange={setListening}
            launchAtLogin={launchAtLogin}
            onLaunchAtLoginChange={setLaunchAtLogin}
          />
        </div>
        <div className="mt-7 flex justify-end">
          <button
            type="button"
            onClick={acknowledge}
            className="rounded-lg bg-white px-6 py-2.5 text-sm font-medium text-black transition-opacity hover:opacity-90"
          >
            Got it
          </button>
        </div>
      </div>
    </div>
  )
}
