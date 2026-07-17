// Source of truth for the main process's Windows caption-button overlay
// (titleBarOverlay) colors. Kept in sync with the CSS tokens in styles/globals.css:
//   APP_BG_HEX === --bg-primary    (#0f0f0f) — also the Mica tint base painted by
//                 the `html[data-mica='true']` rule (rgba(15,15,15,0.82)).
//   WCO_SYMBOL === --text-tertiary (#b0b0b0)
// The caption-cluster BACKGROUND must equal the app background so it's seamless;
// the caption GLYPHS use a distinct legible shade so the buttons stay visible.
// (The renderer's Mica tint lives entirely in CSS — see globals.css — so it
// needs no JS constant; only the main process, which can't read CSS, does.)

/** App base background — the flat canvas / Mica tint base. Equals --bg-primary. */
export const APP_BG_HEX = '#0f0f0f'

/** Home "stage" background — the DARKER paper the Hub paints (equals --home-paper).
 *  Home is the one route whose canvas is darker than the app base, so on Home the
 *  caption overlay switches to this tone; otherwise the WCO cluster reads as a
 *  lighter box over the near-black stage. Every other route uses APP_BG_HEX. */
export const HOME_BG_HEX = '#050505'

/** Caption-button glyph color — deliberately distinct from the seamless
 *  background so min/maximize/close stay legible. Equals --text-tertiary. */
export const WCO_SYMBOL_HEX = '#b0b0b0'
