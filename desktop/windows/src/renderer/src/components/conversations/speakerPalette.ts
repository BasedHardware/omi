// The transcript speaker/bubble palette, ported VERBATIM from macOS `OmiColors`.
//
// READ THIS BEFORE CHANGING ANYTHING HERE.
//
// These are deliberately NOT design-system tokens, and must never become any.
// Track 5 removed the app-wide `purple.*` Tailwind family and set
// `--accent: #ffffff`; the Windows accent system is white/neutral (INV-UI-1).
// The values below are the one sanctioned exception: Chris's binding Track 4
// ruling is that Mac's transcript palette "ports as-is" where Mac renders purple
// (see docs/mac-parity-audit/TRACK4-PLAN.md). PR1 already shipped #8B5CF6 in the
// Rewind search highlight on the same reasoning.
//
// Keeping the whole palette in this single local module is the containment
// boundary: nothing here is exposed as a global token or CSS var, so purple
// cannot leak into surfaces where Mac renders neutral (which the ruling forbids).
// If you need one of these colors, import it from here — do not re-declare a hex
// inline, and do not add a `--accent`-style variable for it.
//
// Not a CI concern either way: the INV-UI-1 brand ratchet
// (.github/scripts/check_brand_ui.py) scans only desktop/macos, app/lib and web/
// — never desktop/windows.

/** Mac's 6 dark speaker tones (`OmiColors.speakerColors`), indexed by speakerId % 6. */
export const SPEAKER_COLORS = [
  '#2D3748', // 0 dark blue-gray
  '#1E3A5F', // 1 navy
  '#2D4A3E', // 2 dark teal
  '#4A3728', // 3 dark brown
  '#3D2E4A', // 4 dark purple
  '#4A3A2D' // 5 dark amber
] as const

/** Fill for the user's own bubbles (Mac `OmiColors.userBubble`). */
export const USER_BUBBLE = '#43389F'

/** Avatar fill for the user — Mac's `purplePrimary`. */
export const AVATAR_USER = '#8B5CF6'

/** Avatar fill for a named person — Mac's `purplePrimary` at 30%. */
export const AVATAR_PERSON = 'rgba(139, 92, 246, 0.3)'

/**
 * Avatar fill for a speaker nobody has named yet — Mac's
 * `backgroundQuaternary` (0x35343B).
 *
 * NOTE this is Mac's literal, NOT the Windows `--bg-quaternary` token (#343438).
 * The near-identical digits are a coincidence between two different colors, not
 * the same value transposed — do not "fix" this to the Windows token. The bubble
 * palette is ported as one cohesive set.
 */
export const AVATAR_UNNAMED = '#35343B'
