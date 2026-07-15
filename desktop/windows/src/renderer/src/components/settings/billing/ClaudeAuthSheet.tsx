import { useEffect, useState } from 'react'
import { Modal } from '../../ui/Modal'
import { onClaudeSignIn, dismissClaudeSignIn, OMI_PRICING_URL } from '../../../lib/claudeSignIn'

// "Upgrade to Omi Pro" sheet — Windows port of macOS ClaudeAuthSheet. Shown by
// beginClaudeSignIn() alongside the parallel Claude OAuth browser launch. This
// is an unconditional upsell (no entitlement check, matching macOS); completing
// the parallel sign-in auto-closes it and grants Claude with no purchase.
// Copy/intent match macOS verbatim; the primary CTA opens omi.me/pricing.
// Neutral white primary, no purple (INV-UI-1). Mounted once at the app root.
export function ClaudeAuthSheet(): React.JSX.Element {
  const [open, setOpen] = useState(false)

  useEffect(() => onClaudeSignIn((s) => setOpen(s.open)), [])

  const onUpgrade = (): void => {
    dismissClaudeSignIn()
    void window.omi.openExternalUrl(OMI_PRICING_URL)
  }

  return (
    <Modal
      open={open}
      onOpenChange={(next) => {
        if (!next) dismissClaudeSignIn()
      }}
      title="Upgrade to Omi Pro"
      size="sm"
      footer={
        <>
          <button
            onClick={dismissClaudeSignIn}
            className="rounded-2xl px-4 py-2 text-sm font-medium text-text-tertiary transition hover:text-text-secondary"
          >
            Cancel
          </button>
          <button
            onClick={onUpgrade}
            className="rounded-2xl bg-white px-4 py-2 text-sm font-semibold text-black transition hover:opacity-90"
          >
            Upgrade to Omi Pro
          </button>
        </>
      }
    >
      <p className="text-text-secondary">Unlock Omi Pro for $199/month</p>
      <p className="mt-2 text-text-tertiary">
        Your browser will open to the Omi Pro checkout. After subscribing, return to omi.
      </p>
      <p className="mt-3 text-xs text-text-tertiary">Complete sign-in in your browser…</p>
    </Modal>
  )
}
