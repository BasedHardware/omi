/**
 * Guards identifiers before they are used as Firestore document paths.
 *
 * Next.js decodes dynamic route segments, so `params.id` can arrive as
 * `a/b`. `collection('users').doc('a/b')` then builds an odd-segment path
 * that throws, or an even-segment path that silently points at a different
 * document. Encoding is NOT the right fix here: the document id must match
 * the raw value the backend stored (Firebase uids may legitimately contain
 * characters like `:` or `@`), so this guard rejects instead of rewriting.
 *
 * Mirrors Firestore's own document-id rules: no `/`, no lone `.`/`..`,
 * no `__*__` reserved ids.
 */
export function isSafeDocumentId(id) {
  return (
    typeof id === 'string' &&
    id.length > 0 &&
    !id.includes('/') &&
    id !== '.' &&
    id !== '..' &&
    !/^__.*__$/.test(id)
  );
}
