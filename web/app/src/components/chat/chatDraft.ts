/**
 * Composer drafts survive a page close or refresh. The persisted copy is
 * cleared only after a send is accepted; a failed or interrupted send keeps
 * it so the text is restored when the composer mounts again.
 */
export const chatDraftKeys = {
  panel: 'omi.chat.draft.panel',
  home: 'omi.chat.draft.home',
} as const;

export function readChatDraft(key: string): string {
  if (typeof window === 'undefined') return '';
  try {
    return window.localStorage.getItem(key) ?? '';
  } catch {
    return '';
  }
}

export function writeChatDraft(key: string, value: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(key, value);
  } catch {
    // A full or blocked localStorage must never break typing.
  }
}

export function clearChatDraft(key: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(key);
  } catch {
    // Best-effort like the write path.
  }
}
