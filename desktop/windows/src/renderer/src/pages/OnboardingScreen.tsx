import { TitleBar } from '../components/layout/TitleBar'
// Imported DIRECTLY (NOT lazy/Suspense). Code-splitting the Onboarding page
// (commit c226cac, for the three.js bundle win) repeatedly blanked the onboarding
// brain map — wrapping the page in Suspense breaks the BrainGraph render. The
// direct import keeps the map reliable; the bundle-size win is not worth it.
import { Onboarding } from './Onboarding'
import { AppStateProvider } from '../state/AppStateProvider'
import { VoiceHubDriverHost } from '../components/chat/VoiceHubDriverHost'

/**
 * The /onboarding route body (main window only — the route never renders in the
 * bar/capture windows).
 *
 * AppStateProvider + VoiceHubDriverHost mount HERE too, not only in AppShell:
 * the onboarding voice step drives a REAL hold, and with pttHubEnabled on (the
 * default) the bar delegates every hold to this window's hub driver over
 * voiceHub:begin. Without a mounted host that IPC has no listener and the press
 * is silently dropped — the shipped first-run bug where onboarding PTT was dead
 * and only worked after onboarding completed. Mounting it here also warms the
 * hub socket during onboarding, so the user's first in-product press connects
 * fast. Routes are exclusive, so this provider unmounts before AppShell's
 * mounts — never two chat engines at once (INV-CHAT-1).
 *
 * Screen capture during onboarding is owned by the always-alive capture window
 * (it seeds the hot currentScreen cache), so no capture host is mounted here.
 */
export function OnboardingScreen(): React.JSX.Element {
  return (
    <>
      <TitleBar variant="overlay" />
      <AppStateProvider>
        <Onboarding />
        <VoiceHubDriverHost />
      </AppStateProvider>
    </>
  )
}
