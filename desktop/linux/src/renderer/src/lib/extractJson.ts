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
  const brace = t.indexOf('{')
  if (brace !== -1) t = t.slice(brace)
  return t.trim()
}
