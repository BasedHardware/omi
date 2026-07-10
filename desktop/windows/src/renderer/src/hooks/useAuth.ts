import { useEffect, useState } from 'react'
import { auth, onAuthStateChanged } from '../lib/firebase'
import { getBenchUser } from '../lib/dev/benchAuth'
import type { User } from 'firebase/auth'

export function useAuth(): { user: User | null; loading: boolean } {
  // Dev-only perf-bench shortcut (null in production — see lib/dev/benchAuth):
  // inject a deterministic fake user so the authed shell mounts every run.
  const benchUser = getBenchUser()
  const [user, setUser] = useState<User | null>(benchUser)
  const [loading, setLoading] = useState(!benchUser)

  useEffect(() => {
    if (benchUser) return
    const unsub = onAuthStateChanged(auth, (u) => {
      setUser(u)
      setLoading(false)
    })
    return unsub
    // getBenchUser() is a stable per-run constant; re-subscribing is unnecessary.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return { user, loading }
}
