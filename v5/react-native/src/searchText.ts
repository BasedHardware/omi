// Shared search filter over projection `searchableText` fields. An empty (or
// whitespace-only) query matches everything, matching the inline
// `normalized === '' ||` idiom every caller previously repeated.
export function matchesSearchQuery(
  searchableText: string,
  query: string,
): boolean {
  const normalized = query.trim().toLocaleLowerCase();
  return (
    normalized === '' || searchableText.toLocaleLowerCase().includes(normalized)
  );
}
