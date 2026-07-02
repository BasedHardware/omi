// Mirrors DesktopBackendEnvironment.swift: env vars override, production defaults otherwise.
// The Firebase key is the public client key shipped in the Mac app bundle
// (desktop/Desktop/Sources/GoogleService-Info.plist).

const normalize = (raw: string | undefined, fallback: string): string => {
  const v = (raw ?? '').trim()
  if (!v) return fallback
  return v.endsWith('/') ? v : v + '/'
}

export const PRODUCTION_PYTHON_API_URL = 'https://api.omi.me/'
export const PRODUCTION_RUST_API_URL = 'https://desktop-backend-hhibjajaja-uc.a.run.app/'
const FIREBASE_API_KEY_OVERRIDE = (process.env.FIREBASE_API_KEY ?? '').trim()
export const FIREBASE_API_KEY = FIREBASE_API_KEY_OVERRIDE || 'AIzaSyD9dzBdglc7IO9pPDIOvqnCoTis_xKkkC8'

export const PROTOCOL_SCHEME = 'omi-computer'
export const AUTH_REDIRECT_URI = `${PROTOCOL_SCHEME}://auth/callback`

export const CHAT_MODEL = 'claude-sonnet-4-6'

export function pythonBaseURL(override?: string): string {
  return normalize(override || process.env.OMI_PYTHON_API_URL, PRODUCTION_PYTHON_API_URL)
}

export function rustBaseURL(override?: string): string {
  return normalize(override || process.env.OMI_DESKTOP_API_URL, PRODUCTION_RUST_API_URL)
}
