/** Checkout must remain retryable when the browser refuses the new tab. */
export const CHECKOUT_POPUP_BLOCKED =
  'Your browser blocked checkout. Allow pop-ups for Omi, then try again.';

export function openCheckoutWindow(url: string): boolean {
  try {
    return Boolean(window.open(url, '_blank'));
  } catch {
    return false;
  }
}
