import { BrandImage } from '../../../ui/BrandImage'
import calendarLogo from '../../../../assets/brands/google_calendar_logo.png'
import gmailLogo from '../../../../assets/brands/gmail_logo.png'
import obsidianLogo from '../../../../assets/brands/obsidian_logo.png'

// The connector brand mark — the Windows port of macOS's ConnectorBrandIcon. It
// renders each service's REAL logo, sized to sit in ConnectorRow's 34px/radius-9
// box. Google Calendar, Gmail, and Obsidian reuse the exact PNG assets the macOS
// app ships (copied into assets/brands/), for one-to-one parity. macOS draws
// ChatGPT/Claude/Notion from the locally installed app icon — a source Windows
// lacks — so those are faithful inline-SVG logomarks. X has no logo asset on
// either platform: macOS renders the 𝕏 wordmark glyph, and so do we. Drop an
// official `<brand>.png` into assets/brands/ and add it to PNG below to upgrade
// any inline mark to a shipped asset.

export type ConnectorBrand =
  | 'calendar'
  | 'gmail'
  | 'obsidian'
  | 'chatgpt'
  | 'claude'
  | 'notion'
  | 'x'
  | 'sticky'

const PNG: Partial<Record<ConnectorBrand, string>> = {
  calendar: calendarLogo,
  gmail: gmailLogo,
  obsidian: obsidianLogo
}

// OpenAI blossom logomark (ChatGPT). Standard 24×24 path, rendered near-white to
// read on the dark tile — matching the modern monochrome OpenAI mark.
function OpenAIMark(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" className="h-[19px] w-[19px]" aria-hidden role="img">
      <path
        fill="#ececec"
        d="M22.28 9.82a5.98 5.98 0 0 0-.52-4.91 6.05 6.05 0 0 0-6.51-2.9A6.07 6.07 0 0 0 4.98 4.18a5.98 5.98 0 0 0-3.99 2.9 6.05 6.05 0 0 0 .74 7.1 5.98 5.98 0 0 0 .51 4.91 6.05 6.05 0 0 0 6.52 2.9A5.98 5.98 0 0 0 13.26 22a6.06 6.06 0 0 0 5.77-4.21 5.99 5.99 0 0 0 4-2.9 6.06 6.06 0 0 0-.75-7.07zm-9.02 12.6a4.48 4.48 0 0 1-2.88-1.04l.14-.08 4.78-2.76a.79.79 0 0 0 .39-.68v-6.74l2.02 1.17a.07.07 0 0 1 .04.05v5.58a4.5 4.5 0 0 1-4.5 4.5zM3.6 18.23a4.47 4.47 0 0 1-.54-3.01l.14.09 4.78 2.76a.77.77 0 0 0 .78 0l5.84-3.37v2.33a.08.08 0 0 1-.03.06L9.74 22a4.5 4.5 0 0 1-6.14-1.65zM2.34 7.9a4.49 4.49 0 0 1 2.34-1.97V11.6a.77.77 0 0 0 .39.68l5.8 3.35-2.02 1.17a.08.08 0 0 1-.07 0l-4.83-2.79A4.5 4.5 0 0 1 2.34 7.9zm16.6 3.86l-5.84-3.4L15.12 7.2a.08.08 0 0 1 .07 0l4.83 2.79a4.49 4.49 0 0 1-.68 8.1v-5.68a.79.79 0 0 0-.4-.65zm2.01-3.02l-.14-.09-4.77-2.78a.78.78 0 0 0-.79 0L9.42 9.24V6.9a.07.07 0 0 1 .03-.06l4.83-2.78a4.5 4.5 0 0 1 6.68 4.66zM8.32 12.9L6.3 11.73a.08.08 0 0 1-.04-.05V6.1a4.5 4.5 0 0 1 7.38-3.45l-.14.08L8.72 5.5a.79.79 0 0 0-.4.68v6.72zm1.1-2.36l2.6-1.5 2.6 1.5v3l-2.6 1.5-2.6-1.5v-3z"
      />
    </svg>
  )
}

// Anthropic sunburst (Claude), in its clay brand color — a radial burst of tapered
// rays about the centre, the recognizable Claude mark.
function ClaudeMark(): React.JSX.Element {
  const rays = Array.from({ length: 12 }, (_, i) => (i * 360) / 12)
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" aria-hidden role="img">
      <g stroke="#D97757" strokeWidth="1.7" strokeLinecap="round">
        {rays.map((deg) => (
          <line key={deg} x1="12" y1="12" x2="12" y2="3.2" transform={`rotate(${deg} 12 12)`} />
        ))}
      </g>
    </svg>
  )
}

// Notion mark — white rounded square with the black angular "N".
function NotionMark(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" className="h-[19px] w-[19px]" aria-hidden role="img">
      <rect x="2" y="2" width="20" height="20" rx="4.5" fill="#fbfbfa" />
      <path
        d="M8 7.2v9.6M8 7.2l8 9.6M16 7.2v9.6"
        fill="none"
        stroke="#0f0f0f"
        strokeWidth="1.9"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

// X (Twitter) — the wordmark glyph, exactly as macOS renders it (no logo asset).
function XMark(): React.JSX.Element {
  return <span className="text-[15px] font-bold leading-none text-home-ink">𝕏</span>
}

// Windows Sticky Notes — no macOS equivalent (it stands in for Apple Notes). A
// clean folded-note mark in the Sticky Notes yellow.
function StickyMark(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" className="h-[18px] w-[18px]" aria-hidden role="img">
      <path
        d="M4.5 4.5h15v10L14 20H4.5z"
        fill="#F5C518"
        stroke="#F5C518"
        strokeWidth="1"
        strokeLinejoin="round"
      />
      <path d="M14 20v-5.5h5.5" fill="#0f0f0f" opacity="0.18" />
    </svg>
  )
}

export function ConnectorBrandMark({ brand }: { brand: ConnectorBrand }): React.JSX.Element {
  const png = PNG[brand]
  if (png) {
    return <BrandImage src={png} alt="" className="h-[22px] w-[22px] object-contain" />
  }
  switch (brand) {
    case 'chatgpt':
      return <OpenAIMark />
    case 'claude':
      return <ClaudeMark />
    case 'notion':
      return <NotionMark />
    case 'x':
      return <XMark />
    case 'sticky':
      return <StickyMark />
    default:
      // calendar/gmail/obsidian are served by PNG above; this only guards an
      // unreachable path so the return type stays a JSX.Element.
      return <span className="h-[18px] w-[18px]" aria-hidden />
  }
}
