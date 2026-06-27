export function matchesSettingsQuery(text: string, query: string): boolean {
  const normalizedText = text.toLowerCase()
  const words = query.trim().toLowerCase().split(/\s+/).filter(Boolean)

  if (words.length === 0) return true
  return words.every((word) => normalizedText.includes(word))
}
