import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { AlertTriangle, X } from 'lucide-react'
import { onUsageLimit, dismissUsageLimit, type UsageLimitReason } from '../../../lib/usageLimit'
import { requestSettingsTab } from '../../../lib/settingsNav'

// Fixed headline + per-reason body (UsageLimitPopupView parity). Mac's Upgrade
// button is purple and it also offers a "Bring your own keys" action — Windows
// has no BYOK UI, so that button is omitted and Upgrade is the app's neutral
// white primary (INV-UI-1: no purple).
const HEADLINE = "You've hit your monthly limit"

const BODY: Record<UsageLimitReason, string> = {
  transcription:
    "You've hit your monthly limit. Upgrade to make sure your new recordings aren't lost.",
  chat: "You've hit your monthly limit. Upgrade to keep chatting with Omi without restrictions.",
  trial_expired: "You've hit your monthly limit. Upgrade to keep using Omi without restrictions."
}

/**
 * Usage-limit modal. Renders nothing until a reason is raised via
 * showUsageLimit(). "Upgrade" deep-links into the Plan & Usage tab; the X and a
 * backdrop tap dismiss (Mac has no separate "Not now" button). Mounted once at
 * the app root.
 */
export function UsageLimitPopup(): React.JSX.Element | null {
  const [reason, setReason] = useState<UsageLimitReason | null>(null)
  const navigate = useNavigate()

  useEffect(() => onUsageLimit(setReason), [])

  if (!reason) return null

  const onUpgrade = (): void => {
    dismissUsageLimit()
    requestSettingsTab('plan-usage')
    navigate('/settings')
  }

  return (
    <div
      className="fixed inset-0 z-[110] flex items-center justify-center bg-black/55 p-6 backdrop-blur-md"
      onClick={dismissUsageLimit}
    >
      <div
        className="glass-strong relative w-full max-w-[380px] p-6 text-center"
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={dismissUsageLimit}
          className="absolute right-3 top-3 rounded-md p-1 text-white/40 hover:bg-white/10 hover:text-white"
          aria-label="Dismiss"
        >
          <X className="h-4 w-4" />
        </button>
        <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-white/10">
          <AlertTriangle className="h-7 w-7 text-amber-400" strokeWidth={1.9} />
        </div>
        <h2 className="text-lg font-semibold text-text-primary">{HEADLINE}</h2>
        <p className="mt-2 text-sm leading-relaxed text-text-tertiary">{BODY[reason]}</p>
        <button
          onClick={onUpgrade}
          className="mt-6 w-full rounded-2xl bg-white px-4 py-2.5 text-sm font-semibold text-black transition hover:opacity-90"
        >
          Upgrade
        </button>
      </div>
    </div>
  )
}
