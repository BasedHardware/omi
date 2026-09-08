import { useEffect, useState } from 'react'
import { auth, onAuthStateChanged } from '../lib/firebase'
import { getBenchUser } from '../lib/dev/benchAuth'
import { getE2EUser } from '../lib/dev/e2eAuth'
import { reconcileAccountForSignIn } from '../lib/authTeardown'
import { isSecondaryWindow } from '../lib/windowRole'
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
      void (async () => {
        // Account-switch guard (main window only — secondary windows share the
        // same SQLite/localStorage, so one wipe suffices). AWAITED before setUser
        // so the authed shell (and its cache hydration: pageCache, KG, outbox
        // sweep) can't mount until a cross-account wipe has finished.
        if (!isSecondaryWindow()) await reconcileAccountForSignIn(u?.uid ?? null)
        setUser(u)
        setLoading(false)
      })()
    })
    return unsub
    // The fake user is a stable per-run constant; re-subscribing is unnecessary.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { user, loading }
}
