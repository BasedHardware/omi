import { useEffect, useState } from 'react'
import { auth, onAuthStateChanged } from '../lib/firebase'
import { getBenchUser } from '../lib/dev/benchAuth'
import { getE2EUser } from '../lib/dev/e2eAuth'
import type { User } from 'firebase/auth'

export function useAuth(): { user: User | null; loading: boolean } {
  // Injected fake user (null in normal use):
  //   - perf bench (OMI_BENCH, DEV-only — see lib/dev/benchAuth)
  //   - shell E2E (OMI_E2E_FAKE_AUTH, survives prod builds — see lib/dev/e2eAuth)
  // Either mounts the authed shell without a live Firebase session.
  const fakeUser = getE2EUser() ?? getBenchUser()
  const [user, setUser] = useState<User | null>(fakeUser)
  const [loading, setLoading] = useState(!fakeUser)

  useEffect(() => {
    if (fakeUser) return
    const unsub = onAuthStateChanged(auth, (u) => {
      setUser(u)
      setLoading(false)
    })
    return unsub
    // The fake user is a stable per-run constant; re-subscribing is unnecessary.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { user, loading }
}
