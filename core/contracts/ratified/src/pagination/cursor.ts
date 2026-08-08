declare const KeysetCursorBrand: unique symbol;

/** Opaque server-issued cursor. Its bindings and signature remain server-owned. */
export type KeysetCursor = string & { readonly [KeysetCursorBrand]: true };

const KEYSET_CURSOR_PATTERN = /^[\x21-\x7e]{1,4096}$/;

/** Brands an opaque cursor after transport-safe validation; it does not verify authenticity. */
export function parseKeysetCursor(raw: string): KeysetCursor | null {
  return KEYSET_CURSOR_PATTERN.test(raw) ? (raw as KeysetCursor) : null;
}
