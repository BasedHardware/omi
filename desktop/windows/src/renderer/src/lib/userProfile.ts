// Identity + backend sync for the startup wizard. The Omi backend exposes
// PATCH /v1/users/language and POST /v1/users/store-recording-permission, but
// has NO endpoint for the user's own name — so the name is set as the Firebase
// Auth displayName (the closest account-level value). All calls are best-effort;
// the wizard persists values locally regardless and never blocks on these.
import { updateProfile } from 'firebase/auth'
import { auth } from './firebase'
import { omiApi } from './apiClient'

export async function syncLanguage(language: string): Promise<void> {
  await omiApi.patch('/v1/users/language', { language })
}

export async function syncRecordingConsent(allowed: boolean): Promise<void> {
  // FastAPI reads a raw boolean body for this endpoint. Axios only serializes
  // non-object payloads to JSON when the content type is already JSON, so set it
  // explicitly — otherwise the bare boolean is sent unserialized.
  await omiApi.post('/v1/users/store-recording-permission', allowed, {
    headers: { 'Content-Type': 'application/json' }
  })
}

export async function setDisplayName(name: string): Promise<void> {
  const user = auth.currentUser
  if (!user) return
  await updateProfile(user, { displayName: name })
}
