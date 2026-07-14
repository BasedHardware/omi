import { useNavigate } from 'react-router-dom'
import { House } from 'lucide-react'
import { HOME_PATH } from '../../routes/manifest'

// The chrome every non-Home page wears: one small "Home" pill, top-left. A port of
// macOS's PageChromeBar / PageChromeButton (DesktopHomeView.swift:1047-1091), which
// is deliberately spare — no back chevron, no breadcrumb, no page title. macOS
// injects it for every page whose index isn't the dashboard (DesktopHomeView.swift:
// 907-917), Settings included.
//
// Geometry is Mac's, 1:1: bar height 34; button = 12px semibold icon + label,
// 7px gap, 11px/7px padding, capsule. The hover border is macOS's `success` green
// at 0.34 (NOT a brightened neutral) — OmiColors.success.opacity(0.34) on line 1082.
export function PageChromeBar(): React.JSX.Element {
  const navigate = useNavigate()

  return (
    <div className="flex h-[34px] shrink-0 items-center px-[18px] pt-[14px] pb-1">
      <button
        type="button"
        onClick={() => navigate(HOME_PATH)}
        title="Home"
        aria-label="Home"
        className={
          'glass-subtle focus-ring group inline-flex select-none items-center gap-[7px] rounded-full ' +
          'border border-[var(--glass-border)] px-[11px] py-[7px] text-[12px] font-semibold ' +
          'text-[color:var(--text-secondary)] transition-colors ' +
          'hover:border-[color:var(--success)]/[0.34] hover:text-white'
        }
      >
        <House className="h-3 w-3 shrink-0" strokeWidth={2.25} />
        Home
      </button>
    </div>
  )
}
