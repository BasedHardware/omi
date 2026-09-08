// Maps a raw conversation-load failure to friendly copy for the detail page.
// Pure, and kept out of the page module so the page only exports components
// (react-refresh/only-export-components).

// A failed load must never dump a raw axios/Error string into the page body. A
// 404 / "not found" (including the local "Local conversation not found" path)
// reads as gone; anything else is a generic load failure the user can retry.
export function friendlyConversationError(raw: string): string {
  const low = raw.toLowerCase()
  if (low.includes('404') || low.includes('not found')) {
    return 'This conversation no longer exists.'
  }
  return 'Couldn’t load this conversation.'
}
