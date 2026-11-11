import { auth } from './firebase'
import type { XConnectorSession } from '../../../shared/types'

// The X connector runs in main (so the import outlives the panel), but the Firebase
// token lives only in the renderer — so we mint { apiBase, token } here and relay it
// with each X IPC call. Same base the omiApi client targets (/v1/x/* is on the main
// backend). Returns null when signed out.
export async function getXSession(): Promise<XConnectorSession | null> {
  const user = auth.currentUser
  if (!user) return null
  const token = await user.getIdToken()
  return { apiBase: import.meta.env.VITE_OMI_API_BASE as string, token }
}
