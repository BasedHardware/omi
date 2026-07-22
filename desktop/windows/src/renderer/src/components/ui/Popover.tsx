import * as PopoverPrimitive from '@radix-ui/react-popover'
import { cn } from '../../lib/utils'

// Anchored popover primitive (NOT a centered dialog — that is Modal.tsx). Radix
// Popover gives the portal, focus management, Esc/outside-click dismiss, and
// anchored positioning relative to the trigger. The panel scales 0.98→1 + fades
// on entrance (tailwind `popover-in`, keyed on Radix data-state), from the
// anchored transform-origin Radix computes. Mirrors Modal.tsx's card styling
// (same border/bg/radius/shadow tokens) so the two read as one system.
//
// Unlike a DropdownMenu (role="menu"), Popover imposes no keyboard menu-nav, so
// it can host a search field + inline rename inputs without fighting the roving
// tabindex — which is why the chat-history list uses it.

export const Popover = PopoverPrimitive.Root
export const PopoverTrigger = PopoverPrimitive.Trigger
export const PopoverAnchor = PopoverPrimitive.Anchor
export const PopoverClose = PopoverPrimitive.Close

type PopoverContentProps = React.ComponentPropsWithoutRef<typeof PopoverPrimitive.Content>

/** Portaled, anchored panel. Defaults to opening below the trigger, right-aligned
 *  (`side="bottom" align="end"`) with an 8px offset — override per call. */
export function PopoverContent({
  className,
  align = 'end',
  side = 'bottom',
  sideOffset = 8,
  children,
  ...props
}: PopoverContentProps): React.JSX.Element {
  return (
    <PopoverPrimitive.Portal>
      <PopoverPrimitive.Content
        align={align}
        side={side}
        sideOffset={sideOffset}
        className={cn(
          'z-[100] w-80 rounded-[var(--radius-card)] border border-white/10 bg-[var(--bg-secondary)] shadow-[0_16px_48px_rgba(0,0,0,0.5)] data-[state=open]:animate-popover-in',
          className
        )}
        style={{ transformOrigin: 'var(--radix-popover-content-transform-origin)' }}
        {...props}
      >
        {children}
      </PopoverPrimitive.Content>
    </PopoverPrimitive.Portal>
  )
}
