const SEARCH_FIELDS = ['ocr_text', 'window_title', 'app'] as const

export const REWIND_SEARCH_TOKEN_LIMIT = 8
export const REWIND_SEARCH_QUERY_CHAR_LIMIT = 512

export type RewindSearchSql = {
  where: string
  params: string[]
}

export function tokenizeRewindSearchQuery(query: string): string[] {
  return query
    .trim()
    .slice(0, REWIND_SEARCH_QUERY_CHAR_LIMIT)
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, REWIND_SEARCH_TOKEN_LIMIT)
}

export function escapeRewindSearchLikeToken(token: string): string {
  return token.replace(/[\\%_]/g, (ch) => `\\${ch}`)
}

export function buildRewindSearchQuery(query: string): RewindSearchSql | null {
  const tokens = tokenizeRewindSearchQuery(query)
  if (tokens.length === 0) return null

  const params: string[] = []
  const clauses = tokens.map((token) => {
    const pattern = `%${escapeRewindSearchLikeToken(token)}%`
    SEARCH_FIELDS.forEach(() => params.push(pattern))
    return `(${SEARCH_FIELDS.map((field) => `${field} LIKE ? ESCAPE '\\'`).join(' OR ')})`
  })

  return {
    where: clauses.join(' AND '),
    params
  }
}
