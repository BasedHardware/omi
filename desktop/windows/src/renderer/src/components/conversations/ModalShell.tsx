import { useEffect } from 'react'

// Windows-native centered modal with a blurred scrim (the app's established
// pattern — see UsageLimitPopup). Mac uses titlebar sheets; the Track 4 ruling is
// to render these as clean centered dialogs instead. Backdrop click and Escape
// dismiss; content clicks don't propagate to the scrim.
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
  useEffect(() => {
    const onKey = (e: KeyboardEvent): void => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [onClose])

  return (
    <div
      className="fixed inset-0 z-[120] flex items-center justify-center bg-black/55 p-6 backdrop-blur-md"
      onClick={onClose}
    >
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
        className={`glass-strong relative w-full ${maxWidth} p-6`}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  )
}
