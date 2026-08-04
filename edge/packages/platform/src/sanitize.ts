/** Wire-compatible with backend/utils/log_sanitizer.py */

const EMAIL_PATTERN = /[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}/g;
const TOKEN_CHARS = /[A-Za-z0-9+/_\-]{8,}/g;

function maskEmail(email: string): string {
  const at = email.indexOf("@");
  const local = email.slice(0, at);
  const domain = email.slice(at + 1);
  if (local.length <= 2) return `***@${domain}`;
  return `${local[0]}***${local[local.length - 1]}@${domain}`;
}

function maskToken(token: string): string {
  if (![...token].some((c) => "0123456789+/".includes(c))) return token;
  const length = token.length;
  if (length < 8) return token;
  if (length <= 12) return `${token.slice(0, 3)}***${token.slice(-3)}`;
  return `${token.slice(0, 4)}***${token.slice(-4)}`;
}

export function sanitize(value: unknown): string {
  if (value === null || value === undefined) return "None";
  let text = String(value);
  if (text.length > 2000) text = `${text.slice(0, 2000)}...[truncated]`;
  text = text.replace(EMAIL_PATTERN, (m) => maskEmail(m));
  return text.replace(TOKEN_CHARS, (m) => maskToken(m));
}

export function sanitizePii(value: unknown): string {
  if (value === null || value === undefined) return "None";
  let text = String(value);
  const truncated = text.length > 200;
  if (truncated) text = text.slice(0, 200);
  text = text.replace(EMAIL_PATTERN, (m) => maskEmail(m));
  const words = text.split(/\s+/);
  const masked = words.map((word) => {
    if (word.includes("@")) return word;
    const n = word.length;
    if (n <= 4) return "***";
    if (n <= 8) return `${word[0]}***${word[n - 1]}`;
    return `${word.slice(0, 2)}***${word.slice(-2)}`;
  });
  let result = masked.join(" ");
  if (truncated) result += "...";
  return result;
}
