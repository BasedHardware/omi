/**
 * Crisp support chat embed.
 *
 * Same website id and embed URL the desktop Help page uses
 * (`desktop/macos/Desktop/Sources/MainWindow/HelpPage.swift`). The id is a
 * public client-side embed identifier, not a credential.
 */
export const CRISP_WEBSITE_ID = '0dcf3d1f-863d-4576-a534-31f2bb102ae5';

export interface SupportIdentity {
  email?: string | null;
  name?: string | null;
}

/**
 * Build the Crisp embed URL, prefilling who is asking so support does not have
 * to ask. Blank or missing values are omitted rather than sent empty.
 */
export function crispEmbedUrl(identity: SupportIdentity = {}): string {
  const params = new URLSearchParams({ website_id: CRISP_WEBSITE_ID });

  const email = identity.email?.trim();
  if (email) params.set('user_email', email);

  const name = identity.name?.trim();
  if (name) params.set('user_nickname', name);

  return `https://go.crisp.chat/chat/embed/?${params.toString()}`;
}
