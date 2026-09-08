/**
 * Split a Windows window title into its document title and app name. Most titles
 * are "Document - App" (e.g. "Inbox - Gmail - Google Chrome"), so the trailing
 * segment is the app and the rest is the real title. Falls back to `fallbackApp`
 * when there's no separator or the title is empty.
 */
export function parseWindowTitle(
  windowTitle: string,
  fallbackApp: string
): { app: string; title: string } {
  const raw = (windowTitle || '').trim()
  if (!raw) return { app: fallbackApp, title: '' }
  const parts = raw.split(' - ')
  if (parts.length >= 2) {
    const app = parts[parts.length - 1].trim()
    const title = parts.slice(0, -1).join(' - ').trim()
    return { app: app || fallbackApp, title }
  }
  return { app: fallbackApp, title: raw }
}
