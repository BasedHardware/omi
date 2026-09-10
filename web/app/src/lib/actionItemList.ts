/**
 * Insert a newly created action item at the front of the list.
 *
 * If the API replayed an existing id (legacy description-hash idempotency),
 * replace that row instead of prepending a ghost duplicate that vanishes on
 * reload.
 */
export function prependOrReplaceById<T extends { id: string }>(items: T[], item: T): T[] {
  const index = items.findIndex((existing) => existing.id === item.id);
  if (index === -1) {
    return [item, ...items];
  }
  const next = items.slice();
  next[index] = item;
  return next;
}
