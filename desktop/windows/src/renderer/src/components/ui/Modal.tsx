import * as Dialog from '@radix-ui/react-dialog'
import { cn } from '../../lib/utils'

type ModalSize = 'sm' | 'md' | 'lg'

const sizeClasses: Record<ModalSize, string> = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg'
}

type ModalProps = {
  open: boolean
  onOpenChange: (open: boolean) => void
  title?: string
  children: React.ReactNode
  // Right-aligned button row (e.g. a Cancel/Confirm pair).
  footer?: React.ReactNode
  size?: ModalSize
  // Destructive/blocking variant: outside-click and Esc no longer dismiss, so a
  // choice must be made via a button. Defaults to a normal dismissible dialog.
  dismissible?: boolean
}

// Centered Fluent ContentDialog (NOT a Mac titlebar-attached sheet). Radix Dialog
// gives the scrim, focus-trap, Esc/outside-click dismiss, and portal. The card
// scales 0.96→1 + fades on entrance (tailwind `modal-in`, keyed on Radix
// data-state). Centering lives on a pointer-events-none flex wrapper so the
// entrance transform is free of translate-centering conflicts.
export function Modal({
  open,
  onOpenChange,
  title,
  children,
  footer,
  size = 'md',
  dismissible = true
}: ModalProps): React.JSX.Element {
  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange}>
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 z-[100] bg-black/50 data-[state=open]:animate-modal-overlay-in" />
        <div className="pointer-events-none fixed inset-0 z-[100] flex items-center justify-center p-6">
          <Dialog.Content
            aria-describedby={undefined}
            onInteractOutside={(e) => {
              if (!dismissible) e.preventDefault()
            }}
            onEscapeKeyDown={(e) => {
              if (!dismissible) e.preventDefault()
            }}
            className={cn(
              'pointer-events-auto w-full rounded-[var(--radius-card)] border border-white/10 bg-[var(--bg-secondary)] p-6 shadow-[0_16px_48px_rgba(0,0,0,0.5)] data-[state=open]:animate-modal-in',
              sizeClasses[size]
            )}
          >
            {/* Radix requires a Title for a11y; hide it visually when none is set. */}
            <Dialog.Title className={cn(title ? 'text-lg font-semibold text-white' : 'sr-only')}>
              {title ?? 'Dialog'}
            </Dialog.Title>
            <div className={cn('text-sm text-white/70', title && 'mt-2')}>{children}</div>
            {footer && <div className="mt-6 flex items-center justify-end gap-2">{footer}</div>}
          </Dialog.Content>
        </div>
      </Dialog.Portal>
    </Dialog.Root>
  )
}
