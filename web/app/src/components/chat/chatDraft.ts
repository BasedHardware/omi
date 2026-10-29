/**
 * Composer drafts survive a page close or refresh. The persisted copy is
 * cleared only after a send is accepted; a failed or interrupted send keeps
 * it so the text is restored when the composer mounts again.
 *
 * Drafts are scoped to the signed-in account: switching accounts (or signing
 * out) clears the previous account's drafts, so one account's unsent prompt
 * is never restored — or sent — from another account's composer.
 */
const baseKeys = {
  panel: 'omi.chat.draft.panel',
  home: 'omi.chat.draft.home',
} as const;

let owner = '';

function scopedKey(base: string): string {
  return owner ? `${base}:${owner}` : base;
}

/** Called by the auth provider whenever the signed-in account changes. */
export function setChatDraftOwner(uid: string | null): void {
  const next = uid ?? '';
  if (next === owner) return;
  if (owner) {
    clearChatDraft(baseKeys.panel);
    clearChatDraft(baseKeys.home);
  }
  owner = next;
}

/** The owner the current draft keys are scoped to ('' while signed out). */
export function chatDraftOwner(): string {
  return owner;
}

export const chatDraftKeys = baseKeys;

export function readChatDraft(key: string): string {
  if (typeof window === 'undefined') return '';
  try {
    return window.localStorage.getItem(scopedKey(key)) ?? '';
  } catch {
    return '';
  }
}

export function writeChatDraft(key: string, value: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(scopedKey(key), value);
  } catch {
    // A full or blocked localStorage must never break typing.
  }
}

export function clearChatDraft(key: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.removeItem(scopedKey(key));
  } catch {
    // Best-effort like the write path.
  }
}
