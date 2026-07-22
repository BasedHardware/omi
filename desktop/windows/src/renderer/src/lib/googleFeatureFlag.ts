// Whether the CLIENT-SIDE Google lane (Gmail via loopback OAuth) is configured for
// this build. The Google client id lives main-side (MAIN_VITE_GOOGLE_CLIENT_ID);
// the renderer can only see this build/runtime flag, which packaged builds leave
// unset by default. Shared by the Settings → Integrations row and the Hub
// Connections panel's Email card so the gate is defined in exactly one place.
//
// NOTE: this gates ONLY the client-side Gmail lane. The Calendar card uses the
// backend-mediated google_calendar OAuth lane, which needs no client creds.
export const GOOGLE_ENABLED =
  import.meta.env.VITE_ENABLE_GOOGLE_INTEGRATION === '1' ||
  (import.meta.env.DEV && localStorage.getItem('omi.google.enabled') === '1')
