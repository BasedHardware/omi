/** Split long text into screen-sized pages.
 *
 *  The G2 has no scrollbar and no way to ask how much text fit, so the app
 *  chops the text itself and pages with the touchpad. Breaks land on a
 *  paragraph, then a space, and only cut mid-word when a single word is longer
 *  than a whole page.
 */
import { PAGE_CHARS } from './config.ts'

export function paginate(text: string, limit: number = PAGE_CHARS): string[] {
  const normalized = text.replace(/\r\n/g, '\n').trim()
  if (normalized.length === 0) return ['']
  if (normalized.length <= limit) return [normalized]

  const pages: string[] = []
  let rest = normalized

  while (rest.length > limit) {
    const window = rest.slice(0, limit + 1)

    // Prefer a paragraph break, then any whitespace, then a hard cut. The
    // `> limit * 0.5` guard stops an early newline from producing a page that
    // is mostly blank.
    let cut = window.lastIndexOf('\n\n')
    if (cut <= limit * 0.5) cut = window.lastIndexOf('\n')
    if (cut <= limit * 0.5) cut = window.lastIndexOf(' ')
    if (cut <= 0) cut = limit

    pages.push(rest.slice(0, cut).trimEnd())
    rest = rest.slice(cut).trimStart()
  }

  if (rest.length > 0) pages.push(rest)
  return pages
}

/** Clamp a page index into range; an empty list still yields page 0. */
export function clampPage(index: number, pageCount: number): number {
  if (pageCount <= 0) return 0
  return Math.max(0, Math.min(index, pageCount - 1))
}
