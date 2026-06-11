import { useEffect, useState } from 'react'
import { auth, onAuthStateChanged } from '../lib/firebase'
import type { User } from 'firebase/auth'

// A minimal fake user used ONLY under the perf bench (OMI_BENCH=1). A live
// Firebase session can't survive a repeated bench loop — the project invalidates
// the refresh token after a few refreshes — so we inject a deterministic user
// instead. This mounts the authed shell (AppShellInner + MainViews) every run,
// exercising the real startup/mount path we optimize. It has NO valid token, so
// api.omi.me calls 401 (panels render empty); that data is fetched async after
// app-ready and isn't part of the startup cost we measure.
const BENCH_USER = {
  uid: 'bench-user',
  email: 'bench@local',
  displayName: 'Bench User',
  getIdToken: async () => 'bench-token'
} as unknown as User

export function useAuth(): { user: User | null; loading: boolean } {
  const isBench = !!window.omi?.isBench
  const [user, setUser] = useState<User | null>(isBench ? BENCH_USER : null)
  const [loading, setLoading] = useState(!isBench)

  useEffect(() => {
    if (isBench) return
    const unsub = onAuthStateChanged(auth, (u) => {
      setUser(u)
      setLoading(false)
    })
    return unsub
  }, [isBench])

  return { user, loading }
}
