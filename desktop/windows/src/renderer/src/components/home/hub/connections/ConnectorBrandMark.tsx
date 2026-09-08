import { BrandImage } from '../../../ui/BrandImage'
import calendarLogo from '../../../../assets/brands/google_calendar_logo.png'
import gmailLogo from '../../../../assets/brands/gmail_logo.png'
import obsidianLogo from '../../../../assets/brands/obsidian_logo.png'
import openclawLogo from '../../../../assets/brands/openclaw_logo.png'
import hermesLogo from '../../../../assets/brands/hermes_logo.png'
import geminiLogo from '../../../../assets/brands/gemini_logo.png'

// The connector brand mark — the Windows port of macOS's ConnectorBrandIcon. It
// renders each service's REAL logo, sized to sit in ConnectorRow's 34px/radius-9
// box. Google Calendar, Gmail, Obsidian, OpenClaw, Hermes, and Gemini reuse the exact
// PNG assets the macOS app ships (copied into assets/brands/), for one-to-one parity.
// macOS draws ChatGPT/Claude/Notion from the locally installed app icon — a source
// Windows lacks — so those are faithful inline logomarks using each brand's official
// vector: ChatGPT the OpenAI knot path, Claude the Anthropic spark, Notion the real
// two-tone logomark. None are hand-drawn approximations. X has no logo asset
// on either platform: macOS renders the 𝕏 wordmark glyph, and so do we. The `omi`
// mark (Ask Omi / Omi Device) is an inline white dot-ring — the shipped omi-mark.png
// is black-on-transparent and would vanish on the dark tile. Drop an official
// `<brand>.png` into assets/brands/ and add it to PNG below to upgrade any inline
// mark to a shipped asset.

export type ConnectorBrand =
  | 'calendar'
  | 'gmail'
  | 'obsidian'
  | 'chatgpt'
  | 'claude'
  | 'notion'
  | 'x'
  | 'sticky'
  | 'openclaw'
  | 'hermes'
  | 'gemini'
  | 'omi'

const PNG: Partial<Record<ConnectorBrand, string>> = {
  calendar: calendarLogo,
  gmail: gmailLogo,
  obsidian: obsidianLogo,
  openclaw: openclawLogo,
  hermes: hermesLogo,
  // The exact real Gemini logo the macOS app ships (copied from its Resources), so the
  // Gemini memory-pack row shows the true four-colour spark instead of a placeholder.
  gemini: geminiLogo
}

// OpenAI blossom logomark (ChatGPT), rendered near-white to read on the dark tile —
// matching the modern monochrome OpenAI mark. This is the official knot path; the
// earlier version was a lossy two-decimal retype of it whose rounding left a visible
// notch ("chip") in the upper-left lobe. macOS draws ChatGPT from the installed app
// icon (a clean mark), so this restores parity — the chip was a Windows-only artifact.
function OpenAIMark(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" className="h-full w-full" aria-hidden role="img">
      <path
        fill="#ececec"
        d="M22.2819 9.8211a5.9847 5.9847 0 0 0-.5157-4.9108 6.0462 6.0462 0 0 0-6.5098-2.9A6.0651 6.0651 0 0 0 4.9807 4.1818a5.9847 5.9847 0 0 0-3.9977 2.9 6.0462 6.0462 0 0 0 .7427 7.0966 5.98 5.98 0 0 0 .511 4.9107 6.051 6.051 0 0 0 6.5146 2.9001A5.9847 5.9847 0 0 0 13.2599 24a6.0557 6.0557 0 0 0 5.7718-4.2058 5.9894 5.9894 0 0 0 3.9977-2.9001 6.0557 6.0557 0 0 0-.7475-7.0729zm-9.022 12.6081a4.4755 4.4755 0 0 1-2.8764-1.0408l.1419-.0804 4.7783-2.7582a.7948.7948 0 0 0 .3927-.6813v-6.7369l2.02 1.1686a.071.071 0 0 1 .038.052v5.5826a4.504 4.504 0 0 1-4.4945 4.4944zm-9.6607-4.1254a4.4708 4.4708 0 0 1-.5346-3.0137l.142.0852 4.783 2.7582a.7712.7712 0 0 0 .7806 0l5.8428-3.3685v2.3324a.0804.0804 0 0 1-.0332.0615L9.74 19.9502a4.4992 4.4992 0 0 1-6.1408-1.6464zM2.3408 7.8956a4.485 4.485 0 0 1 2.3655-1.9728V11.6a.7664.7664 0 0 0 .3879.6765l5.8144 3.3543-2.0201 1.1685a.0757.0757 0 0 1-.071 0l-4.8303-2.7865A4.504 4.504 0 0 1 2.3408 7.872zm16.5963 3.8558L13.1038 8.364 15.1192 7.2a.0757.0757 0 0 1 .071 0l4.8303 2.7913a4.4944 4.4944 0 0 1-.6765 8.1042v-5.6772a.79.79 0 0 0-.407-.667zm2.0107-3.0231l-.142-.0852-4.7735-2.7818a.7759.7759 0 0 0-.7854 0L9.409 9.2297V6.8974a.0662.0662 0 0 1 .0284-.0615l4.8303-2.7866a4.4992 4.4992 0 0 1 6.6802 4.66zM8.3065 12.863l-2.02-1.1638a.0804.0804 0 0 1-.038-.0567V6.0742a4.4992 4.4992 0 0 1 7.3757-3.4537l-.142.0805L8.704 5.459a.7948.7948 0 0 0-.3927.6813zm1.0976-2.3654l2.602-1.4998 2.6069 1.4998v2.9994l-2.5974 1.4997-2.6067-1.4997Z"
      />
    </svg>
  )
}

// Claude — the official Anthropic "spark" logomark in its clay brand colour, the same
// mark macOS shows from the installed Claude.app icon. Replaces an earlier hand-drawn
// twelve-ray approximation with the real asymmetric burst path.
function ClaudeMark(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" className="h-full w-full" aria-hidden role="img">
      <path
        fill="#D97757"
        d="m4.7144 15.9555 4.7174-2.6471.079-.2307-.079-.1275h-.2307l-.7893-.0486-2.6956-.0729-2.3375-.0971-2.2646-.1214-.5707-.1215-.5343-.7042.0546-.3522.4797-.3218.686.0608 1.5179.1032 2.2767.1578 1.6514.0972 2.4468.255h.3886l.0546-.1579-.1336-.0971-.1032-.0972L6.973 9.8356l-2.55-1.6879-1.3356-.9714-.7225-.4918-.3643-.4614-.1578-1.0078.6557-.7225.8803.0607.2246.0607.8925.686 1.9064 1.4754 2.4893 1.8336.3643.3035.1457-.1032.0182-.0728-.164-.2733-1.3539-2.4467-1.445-2.4893-.6435-1.032-.17-.6194c-.0607-.255-.1032-.4674-.1032-.7285L6.287.1335 6.6997 0l.9957.1336.419.3642.6192 1.4147 1.0018 2.2282 1.5543 3.0296.4553.8985.2429.8318.091.255h.1579v-.1457l.1275-1.706.2368-2.0947.2307-2.6957.0789-.7589.3764-.9107.7468-.4918.5828.2793.4797.686-.0668.4433-.2853 1.8517-.5586 2.9021-.3643 1.9429h.2125l.2429-.2429.9835-1.3053 1.6514-2.0643.7286-.8196.85-.9046.5464-.4311h1.0321l.759 1.1293-.34 1.1657-1.0625 1.3478-.8804 1.1414-1.2628 1.7-.7893 1.36.0729.1093.1882-.0183 2.8535-.607 1.5421-.2794 1.8396-.3157.8318.3886.091.3946-.3278.8075-1.967.4857-2.3072.4614-3.4364.8136-.0425.0304.0486.0607 1.5482.1457.6618.0364h1.621l3.0175.2247.7892.522.4736.6376-.079.4857-1.2142.6193-1.6393-.3886-3.825-.9107-1.3113-.3279h-.1822v.1093l1.0929 1.0686 2.0035 1.8092 2.5075 2.3314.1275.5768-.3218.4554-.34-.0486-2.2039-1.6575-.85-.7468-1.9246-1.621h-.1275v.17l.4432.6496 2.3436 3.5214.1214 1.0807-.17.3521-.6071.2125-.6679-.1214-1.3721-1.9246L14.38 17.959l-1.1414-1.9428-.1397.079-.674 7.2552-.3156.3703-.7286.2793-.6071-.4614-.3218-.7468.3218-1.4753.3886-1.9246.3157-1.53.2853-1.9004.17-.6314-.0121-.0425-.1397.0182-1.4328 1.9672-2.1796 2.9446-1.7243 1.8456-.4128.164-.7164-.3704.0667-.6618.4008-.5889 2.386-3.0357 1.4389-1.882.929-1.0868-.0062-.1579h-.0546l-6.3385 4.1164-1.1293.1457-.4857-.4554.0608-.7467.2307-.2429 1.9064-1.3114Z"
      />
    </svg>
  )
}

// Notion mark — the real Notion logomark (the recognizable page + angular "N"),
// the same official two-tone artwork the App Marketplace shows. The white page path
// (#fff) reads as a light app-icon square on the dark tile; the black path (#000)
// is the page border and "N". Replaces the earlier hand-drawn three-stroke "N" that
// looked like a plain letter avatar next to the marketplace's real logo.
function NotionMark(): React.JSX.Element {
  return (
    <svg viewBox="0 0 100 100" className="h-full w-full" aria-hidden role="img">
      <path
        d="M6.017 4.313l55.333 -4.087c6.797 -0.583 8.543 -0.19 12.817 2.917l17.663 12.443c2.913 2.14 3.883 2.723 3.883 5.053v68.243c0 4.277 -1.553 6.807 -6.99 7.193L24.467 99.967c-4.08 0.193 -6.023 -0.39 -8.16 -3.113L3.3 79.94c-2.333 -3.113 -3.3 -5.443 -3.3 -8.167V11.113c0 -3.497 1.553 -6.413 6.017 -6.8z"
        fill="#fff"
      />
      <path
        fillRule="evenodd"
        clipRule="evenodd"
        d="M61.35 0.227l-55.333 4.087C1.553 4.7 0 7.617 0 11.113v60.66c0 2.723 0.967 5.053 3.3 8.167l13.007 16.913c2.137 2.723 4.08 3.307 8.16 3.113l64.257 -3.89c5.433 -0.387 6.99 -2.917 6.99 -7.193V20.64c0 -2.21 -0.873 -2.847 -3.443 -4.733L74.167 3.143c-4.273 -3.107 -6.02 -3.5 -12.817 -2.917zM25.92 19.523c-5.247 0.353 -6.437 0.433 -9.417 -1.99L8.927 11.507c-0.77 -0.78 -0.383 -1.753 1.557 -1.947l53.193 -3.887c4.467 -0.39 6.793 1.167 8.54 2.527l9.123 6.61c0.39 0.197 1.36 1.36 0.193 1.36l-54.933 3.307 -0.68 0.047zM19.803 88.3V30.367c0 -2.53 0.777 -3.697 3.103 -3.893L86 22.78c2.14 -0.193 3.107 1.167 3.107 3.693v57.547c0 2.53 -0.39 4.67 -3.883 4.863l-60.377 3.5c-3.493 0.193 -5.043 -0.97 -5.043 -4.083zm59.6 -54.827c0.387 1.75 0 3.5 -1.75 3.7l-2.91 0.577v42.773c-2.527 1.36 -4.853 2.137 -6.797 2.137 -3.107 0 -3.883 -0.973 -6.21 -3.887l-19.03 -29.94v28.967l6.02 1.363s0 3.5 -4.857 3.5l-13.39 0.777c-0.39 -0.78 0 -2.723 1.357 -3.11l3.497 -0.97v-38.3L30.48 40.667c-0.39 -1.75 0.58 -4.277 3.3 -4.473l14.367 -0.967 19.8 30.327v-26.83l-5.047 -0.58c-0.39 -2.143 1.163 -3.7 3.103 -3.89l13.4 -0.78z"
        fill="#000"
      />
    </svg>
  )
}

// X (Twitter) — the wordmark glyph, exactly as macOS renders it (no logo asset).
// Drawn as SVG text so it scales to fill the brand chip like every other mark.
function XMark(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" className="h-full w-full" aria-hidden role="img">
      <text
        x="12"
        y="12"
        textAnchor="middle"
        dominantBaseline="central"
        fontSize="20"
        fontWeight="700"
        fill="#f0ece3"
      >
        𝕏
      </text>
    </svg>
  )
}

// Windows Sticky Notes — no macOS equivalent (it stands in for Apple Notes). A
// clean folded-note mark in the Sticky Notes yellow.
function StickyMark(): React.JSX.Element {
  return (
    <svg viewBox="0 0 24 24" className="h-full w-full" aria-hidden role="img">
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

// Omi mark — eight white dots in a ring, exactly the shipped omi-mark.png glyph but
// drawn inline in home-ink so it reads on the dark tile (the PNG is black). Used by
// the "Ask Omi" and "Omi Device" tray rows, matching macOS's HomeOmiMarkIcon.
function OmiMark(): React.JSX.Element {
  const dots = Array.from({ length: 8 }, (_, i) => {
    const a = (i * Math.PI) / 4
    return { cx: 12 + 6.6 * Math.sin(a), cy: 12 - 6.6 * Math.cos(a) }
  })
  return (
    <svg viewBox="0 0 24 24" className="h-full w-full" aria-hidden role="img">
      {dots.map((d, i) => (
        <circle key={i} cx={d.cx} cy={d.cy} r="1.55" fill="#f0ece3" />
      ))}
    </svg>
  )
}

export function ConnectorBrandMark({ brand }: { brand: ConnectorBrand }): React.JSX.Element {
  const png = PNG[brand]
  if (png) {
    // Fill the brand chip's inset content box (the chip owns size + padding), so every
    // logo — glyph or full-bleed square — sits within a consistent frame.
    return <BrandImage src={png} alt="" className="h-full w-full object-contain" />
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
    case 'omi':
      return <OmiMark />
    default:
      // calendar/gmail/obsidian/openclaw/hermes/gemini are served by PNG above; this
      // only guards an unreachable path so the return type stays a JSX.Element.
      return <span className="h-[18px] w-[18px]" aria-hidden />
  }
}
