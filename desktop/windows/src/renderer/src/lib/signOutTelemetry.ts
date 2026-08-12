import { trackSignedOut } from './analytics'
import { auth, signOutUser } from './firebase'

/** User-initiated sign-out terminal; auth expiry does not enter this path. */
export async function signOutAndTrack(): Promise<void> {
  const distinctId = auth.currentUser?.uid ?? ''
  await signOutUser()
  trackSignedOut(distinctId)
}
