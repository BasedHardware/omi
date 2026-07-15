import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import { AudioWaveform, Gift, MessageCircle, Mic, Scan, Settings } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { getPreferences, onPreferencesChange, setPreferences } from '../../../lib/preferences'
import { cn } from '../../../lib/utils'
import type { RewindSettings } from '../../../../../shared/types'

// The Hub's top-right controls: a screen-capture pill, a listening pill, and the
// gear menu. Both pills drive the app's REAL capture state — the same
// rewindGetSettings/rewindSetSettings + `continuousRecording` preference the
// sidebar toggles — and both SUBSCRIBE to changes (rewind:settings from main,
// onPreferencesChange for the mic), which is what actually keeps them from
// disagreeing with the sidebar. Reading once on mount would not.
//
// Mac reveals a listening-MODE sub-control on hover. Windows has no
// listening-mode concept, so that sub-control is omitted rather than invented.

const REFER_URL = 'https://affiliate.omi.me'
const DISCORD_URL = 'https://discord.com/invite/8MP3b9ymvx'

// Shared pill states. Mac also has a `blocked` (red) state for a denied capture
// permission; Windows screen capture has no permission gate (RewindSettings
// carries no such field), so that state is unreachable here and is not modeled.
type PillState = 'active' | 'inactive'

const PILL_CLASS: Record<PillState, string> = {
  // The active stroke is CONSTANT — only the fill lifts on hover.
  active: 'bg-home-green/[0.12] hover:bg-home-green/20 border-home-green/[0.38] text-home-ink',
  inactive:
    'bg-home-panel hover:bg-home-tileHover border-home-hairline/[0.58] hover:border-home-hairline/80 text-home-muted'
}

function Pill(props: {
  Icon: LucideIcon
  text: string
  on: boolean
  label: string
  onClick: () => void
}): React.JSX.Element {
  const { Icon, text, on, label, onClick } = props
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={on}
      aria-label={label}
      className={cn(
        'focus-ring flex h-[34px] items-center gap-2 rounded-full border',
        // Leading 12 / trailing 8 — asymmetric, matching Mac.
        'pl-3 pr-2 text-[12px] font-medium transition-colors duration-150',
        PILL_CLASS[on ? 'active' : 'inactive']
      )}
    >
      <Icon className="h-[13px] w-[13px] shrink-0" strokeWidth={2} />
      {text}
    </button>
  )
}

function GearMenu(): React.JSX.Element {
  const navigate = useNavigate()

  const row = (Icon: LucideIcon, label: string, onSelect: () => void): React.JSX.Element => (
    <DropdownMenu.Item
      onSelect={onSelect}
      className="flex cursor-pointer select-none items-center rounded-lg px-[9px] py-[7px] text-[13px] font-medium text-home-ink outline-none data-[highlighted]:bg-home-tileHover"
    >
      <Icon className="mr-2 h-[13px] w-[18px] shrink-0 text-home-secondary" strokeWidth={2.5} />
      {label}
    </DropdownMenu.Item>
  )

  return (
    <DropdownMenu.Root>
      <DropdownMenu.Trigger asChild>
        <button
          type="button"
          aria-label="Home menu"
          className={cn(
            'focus-ring group flex h-[34px] w-[34px] items-center justify-center rounded-full',
            'border border-home-hairline/[0.68] bg-home-tile/[0.86] transition-colors duration-150',
            'hover:border-home-hairline/90 hover:bg-home-tileHover'
          )}
        >
          <Settings
            className="h-[14px] w-[14px] text-home-secondary transition-colors duration-150 group-hover:text-home-ink"
            strokeWidth={2.5}
          />
        </button>
      </DropdownMenu.Trigger>
      <DropdownMenu.Portal>
        <DropdownMenu.Content
          align="end"
          sideOffset={8}
          className="z-50 w-[190px] rounded-xl border border-home-hairline bg-home-panel p-1.5 shadow-[0_16px_40px_rgba(0,0,0,0.5)]"
        >
          {/* External links go through main's shell.openExternal bridge, so they
              open in the user's real browser rather than an Electron window. */}
          {row(Gift, 'Refer a Friend', () => void window.omi?.openExternalUrl?.(REFER_URL))}
          {row(MessageCircle, 'Discord', () => void window.omi?.openExternalUrl?.(DISCORD_URL))}
          <DropdownMenu.Separator className="my-1.5 h-px bg-home-hairline" />
          {row(Settings, 'Settings', () => navigate('/settings'))}
        </DropdownMenu.Content>
      </DropdownMenu.Portal>
    </DropdownMenu.Root>
  )
}

export function HubHeader(): React.JSX.Element {
  // Screen capture — the persistent Rewind setting (see Sidebar: optimistic flip,
  // reconcile from main).
  const [rewind, setRewind] = useState<RewindSettings | null>(null)
  useEffect(() => {
    void window.omi.rewindGetSettings().then(setRewind)
    // SUBSCRIBE, don't just read once. Main broadcasts `rewind:settings` to every
    // window on write, and the sidebar's screen toggle is co-visible with this pill
    // — without this, flipping one leaves the other showing the old state.
    return window.omi.onRewindSettings(setRewind)
  }, [])
  const captureOn = !!rewind?.captureEnabled
  const toggleCapture = (): void => {
    if (!rewind) return
    const next = { ...rewind, captureEnabled: !rewind.captureEnabled }
    setRewind(next)
    void window.omi.rewindSetSettings(next).then(setRewind)
  }

  // Listening — the always-on mic (`continuousRecording`). Subscribed, so a flip
  // from the sidebar or the tray is reflected here immediately.
  const [micOn, setMicOn] = useState<boolean>(() => !!getPreferences().continuousRecording)
  useEffect(() => onPreferencesChange((p) => setMicOn(!!p.continuousRecording)), [])
  const toggleMic = (): void => {
    setPreferences({ continuousRecording: !getPreferences().continuousRecording })
  }

  return (
    <div className="flex h-9 items-center gap-2.5">
      {/* Mac labels these with the FEATURE NAME ("Capture" / "Listening"), not the
          state (DashboardPage.swift HomeStatusButton title:). The on/off state is
          carried by the pill's colour (green when on) and, for listening, the icon
          (mic → waveform) — so the label stays constant and legible, and the aria-label
          still announces the action. Showing "On"/"Off" as the label read as a bare
          toggle with no hint of WHICH control it is. */}
      <Pill
        Icon={Scan}
        text="Capture"
        on={captureOn}
        label={captureOn ? 'Turn screen capture off' : 'Turn screen capture on'}
        onClick={toggleCapture}
      />
      <Pill
        Icon={micOn ? AudioWaveform : Mic}
        text="Listening"
        on={micOn}
        label={micOn ? 'Stop listening' : 'Start listening'}
        onClick={toggleMic}
      />
      <GearMenu />
    </div>
  )
}
