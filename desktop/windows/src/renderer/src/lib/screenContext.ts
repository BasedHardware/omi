// Reads what's on screen RIGHT NOW for the chat: the current screen's OCR text
// (main process hot cache), attached to EVERY message as ambient context so the
// model can answer about the screen when it's relevant. The framing tells the model
// to ignore it unless the message is about the screen, so normal chat isn't bloated.
// Best-effort — on timeout or any failure it returns '' so the message still sends,
// just without screen context.

// Cap the wait so the chat send never stalls on a slow capture/OCR. The main
// handler has its own backstop too; this is the renderer-side ceiling.
const SCREEN_TIMEOUT_MS = 4000
// OCR of a full screen can be long; cap what we prepend so it can't dominate the
// prompt. The model only needs the gist of what's visible.
const MAX_SCREEN_CHARS = 4000

/**
 * Read the current screen's OCR text at send time and frame it as ambient context.
 * Attached to every message (the framing tells the model to ignore it unless the
 * message is about the screen). Best-effort: returns '' on any timeout/failure so
 * the message always sends — just without screen context when none is available.
 */
export async function readCurrentScreen(): Promise<string> {
  try {
    const text = await Promise.race([
      window.omi.screenReadText(),
      new Promise<string>((resolve) => setTimeout(() => resolve(''), SCREEN_TIMEOUT_MS))
    ])
    const trimmed = (text ?? '').trim()
    if (!trimmed) return ''
    const clipped =
      trimmed.length > MAX_SCREEN_CHARS ? `${trimmed.slice(0, MAX_SCREEN_CHARS)}…` : trimmed
    return `[Screen context — OCR of what is on the user's screen right now, provided as background only. Use it ONLY if the user's message is about what is on their screen. If it is not, ignore this completely: do not describe, summarize, or mention the screen.]
${clipped}`
  } catch {
    return ''
  }
}
