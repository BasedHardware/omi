// Rewind search query builder — FTS5 MATCH (BM25-ranked) over `rewind_frames_fts`.
// Ports the macOS `expandSearchQuery` behaviour (RewindDatabase.swift): each
// whitespace token is split on camelCase and digit/non-digit boundaries, the
// original token plus every sub-part (deduped, length >= 2) are prefix-matched
// with a trailing `*` and OR'd, and multiple tokens are AND'd (space = implicit
// AND in FTS5). Windows hardens Mac by quoting every part as an FTS5 phrase so
// user input can never break the MATCH grammar (see `ftsPrefixTerm`).

export const REWIND_SEARCH_TOKEN_LIMIT = 8
export const REWIND_SEARCH_QUERY_CHAR_LIMIT = 512

/** Whitespace-split the raw query, bounded by the char + token limits. */
export function tokenizeRewindSearchQuery(query: string): string[] {
  return query
    .trim()
    .slice(0, REWIND_SEARCH_QUERY_CHAR_LIMIT)
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, REWIND_SEARCH_TOKEN_LIMIT)
}

/** True for a cased letter that is currently uppercase (unicode-aware, unlike
 *  `/[A-Z]/`; digits/punctuation are not "uppercase" since lower === upper). */
function isUpper(ch: string): boolean {
  return ch.toLowerCase() !== ch.toUpperCase() && ch === ch.toUpperCase()
}

/** Split camelCase on uppercase boundaries: "ActivityPerformance" -> [Activity, Performance].
 *  Parts shorter than 2 chars are dropped (matches Mac). */
export function splitCamelCase(word: string): string[] {
  const parts: string[] = []
  let cur = ''
  for (const ch of word) {
    if (isUpper(ch) && cur !== '') {
      parts.push(cur)
      cur = ch
    } else {
      cur += ch
    }
  }
  if (cur !== '') parts.push(cur)
  return parts.filter((p) => p.length >= 2)
}

/** Split on digit/non-digit boundaries: "test123" -> [test, 123]. Parts shorter
 *  than 2 chars are dropped (matches Mac). */
export function splitOnDigits(word: string): string[] {
  const parts: string[] = []
  let cur = ''
  let wasDigit = false
  for (const ch of word) {
    const isDigit = ch >= '0' && ch <= '9'
    if (cur !== '' && isDigit !== wasDigit) {
      parts.push(cur)
      cur = ch
    } else {
      cur += ch
    }
    wasDigit = isDigit
  }
  if (cur !== '') parts.push(cur)
  return parts.filter((p) => p.length >= 2)
}

/** True when the string contains at least one letter or number the FTS5
 *  tokenizer would index (a part of pure punctuation matches nothing). */
function hasAlnum(s: string): boolean {
  return /[\p{L}\p{N}]/u.test(s)
}

/** A single FTS5 prefix term: the part is wrapped in a double-quoted phrase
 *  (internal quotes doubled) so any special characters are treated as literal
 *  token separators rather than query syntax, then a trailing `*` makes it a
 *  prefix query on the phrase's last token. e.g. `Activity` -> `"Activity"*`. */
function ftsPrefixTerm(part: string): string {
  return `"${part.replace(/"/g, '""')}"*`
}

/** Expand one whitespace token into an FTS5 sub-expression, or null when it
 *  carries no indexable content. Insertion order (original word, then camelCase
 *  parts, then digit parts) is preserved and deduped. */
export function expandRewindSearchWord(word: string): string | null {
  const parts = [word, ...splitCamelCase(word), ...splitOnDigits(word)]
  const unique = [...new Set(parts)].filter((p) => p.length >= 2 && hasAlnum(p))
  if (unique.length === 0) return null
  const terms = unique.map(ftsPrefixTerm)
  return terms.length === 1 ? terms[0] : `(${terms.join(' OR ')})`
}

/** Build the full FTS5 MATCH expression for a raw query, or null when the query
 *  has no searchable tokens. Tokens are AND'd (space-joined). */
export function buildRewindFtsMatch(query: string): string | null {
  const expanded = tokenizeRewindSearchQuery(query)
    .map(expandRewindSearchWord)
    .filter((x): x is string => x !== null)
  if (expanded.length === 0) return null
  return expanded.join(' ')
}
