import { useEffect, useRef } from 'react'

// Elements that participate in the keyboard tab order. Disabled controls and
// explicitly untabbable nodes (tabindex="-1", e.g. the dialog container itself)
// are excluded.
const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'

function getFocusable(container: HTMLElement): HTMLElement[] {
  return Array.from(container.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR))
}

// Windows-native centered modal with a blurred scrim (the app's established
// pattern — see UsageLimitPopup). Mac uses titlebar sheets; the Track 4 ruling is
// to render these as clean centered dialogs instead. Backdrop click and Escape
// dismiss; content clicks don't propagate to the scrim. Keyboard focus is trapped
// inside the dialog and restored to the opener on close.
export function ModalShell({
  onClose,
  children,
  maxWidth = 'max-w-[420px]',
  labelledBy
}: {
  onClose: () => void
  children: React.ReactNode
  maxWidth?: string
  labelledBy?: string
}): React.JSX.Element {
  const containerRef = useRef<HTMLDivElement>(null)

  // Capture the element that was focused before the modal opened, DURING render.
  // React applies a child's `autoFocus` in the commit phase — before any effect
  // runs — so by the time an effect fires, document.activeElement is already the
  // modal's own field. Reading it here still sees the opener's trigger, which is
  // what we restore focus to on close. The null-guard makes it a one-shot capture
  // that survives re-renders.
  const restoreFocusRef = useRef<Element | null>(null)
  if (restoreFocusRef.current === null) {
    restoreFocusRef.current = document.activeElement
  }

  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  // Move focus into the dialog on open (unless a child already grabbed it via
  // autoFocus — don't fight it), and restore focus to the opener on unmount.
  useEffect(() => {
    const container = containerRef.current
    if (container && !container.contains(document.activeElement)) {
      const focusables = getFocusable(container)
      ;(focusables[0] ?? container).focus()
    }
    return () => {
      const toRestore = restoreFocusRef.current
      if (toRestore instanceof HTMLElement && toRestore.isConnected) {
        toRestore.focus()
      }
    }
    // Mount/unmount only: capture initial focus and restore it on close.
  }, [])

  // Trap Tab / Shift+Tab so focus wraps inside the dialog and never reaches the
  // page behind the scrim. Recomputed on every keystroke so it stays correct when
  // the modal's focusable set changes (e.g. a control appears or disables).
  const onKeyDownTrap = (e: React.KeyboardEvent<HTMLDivElement>): void => {
    if (e.key !== 'Tab') return
    const container = containerRef.current
    if (!container) return
    const focusables = getFocusable(container)
    if (focusables.length === 0) {
      // Nothing tabbable inside — hold focus on the dialog itself.
      e.preventDefault()
      return
    }
    const first = focusables[0]
    const last = focusables[focusables.length - 1]
    const active = document.activeElement
    if (e.shiftKey) {
      if (active === first || !container.contains(active)) {
        e.preventDefault()
        last.focus()
      }
    } else if (active === last || !container.contains(active)) {
      e.preventDefault()
      first.focus()
    }
  }

  return (
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/55 p-6 backdrop-blur-md"
      onClick={onClose}
    >
      <div
        ref={containerRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        tabIndex={-1}
        onKeyDown={onKeyDownTrap}
        className={`glass-strong relative w-full ${maxWidth} p-6`}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  )
}
