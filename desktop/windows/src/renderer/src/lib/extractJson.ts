// Port of the desktop's extractJSONObject: drop a leading ``` fence (with its
// language line) and a trailing fence, then start at the first '{'. Shared by
// memory extraction and KG synthesis/agent parsing so the fence-stripping logic
// lives in exactly one place.
export function extractJSONObject(text: string): string {
  let t = text.trim()
  if (t.startsWith('```')) {
    const nl = t.indexOf('\n')
    if (nl !== -1) t = t.slice(nl + 1)
    if (t.endsWith('```')) t = t.slice(0, -3).trim()
  }
  const start = t.indexOf('{')
  if (start === -1) return t.trim()
  // Slice to the brace that matches the first '{', ignoring braces inside string
  // values, so trailing prose ("...{...} Hope that helps!") does not break a
  // caller's JSON.parse. Fall back to slice-to-end if the object is never closed.
  let depth = 0
  let inStr = false
  let escaped = false
  for (let i = start; i < t.length; i++) {
    const ch = t[i]
    if (inStr) {
      if (escaped) escaped = false
      else if (ch === '\\') escaped = true
      else if (ch === '"') inStr = false
      continue
    }
    if (ch === '"') inStr = true
    else if (ch === '{') depth++
    else if (ch === '}' && --depth === 0) return t.slice(start, i + 1)
  }
  return t.slice(start).trim()
}
