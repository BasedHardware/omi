/** Must stay in sync with `CONVERSATIONS_PATH` usage in `routes/manifest.ts`. */
export const CONVERSATIONS_PATH = '/conversations'

export function isConversationsPanelActive(pathname: string): boolean {
  return pathname === CONVERSATIONS_PATH
}
