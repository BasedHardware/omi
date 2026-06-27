import { useEffect, useRef, useState } from 'react'
import { auth } from '../lib/firebase'
import type { User } from 'firebase/auth'

const CRISP_WEBSITE_ID = '0dcf3d1f-863d-4576-a534-31f2bb102ae5'

export function Help(): React.JSX.Element {
  const iframeRef = useRef<HTMLIFrameElement>(null)
  const [user, setUser] = useState<User | null>(auth.currentUser)

  useEffect(() => {
    const unsub = auth.onAuthStateChanged((u) => setUser(u))
    return () => unsub()
  }, [])

  const crispUrl = (() => {
    const params = new URLSearchParams()
    if (user?.email) params.set('email', user.email)
    if (user?.displayName) params.set('nickname', user.displayName)
    const query = params.toString()
    return `https://go.crisp.chat/chat/embed/?website_id=${CRISP_WEBSITE_ID}${query ? `&${query}` : ''}`
  })()

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex shrink-0 items-center gap-4 border-b border-white/[0.07] px-6 py-4">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-blue-500/15">
          <span className="text-lg">💬</span>
        </div>
        <div>
          <h1 className="text-lg font-semibold text-text-primary">Help from Founder</h1>
          <p className="text-xs text-text-tertiary">Chat live with the Omi team</p>
        </div>
      </div>

      {/* Crisp chat embed */}
      <div className="relative min-h-0 flex-1 bg-[#0a0a0a]">
        <iframe
          ref={iframeRef}
          src={crispUrl}
          title="Omi Support Chat"
          className="h-full w-full border-0"
          allow="microphone"
        />
      </div>
    </div>
  )
}
