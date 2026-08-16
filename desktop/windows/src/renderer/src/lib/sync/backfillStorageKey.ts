// Leaf module: localStorage key for backfill's post-history dedupe. Kept
// separate from backfill.ts's own body (which pulls in the outbox +
// conversationSync → apiClient → firebase stack) so authTeardown.ts — which
// firebase.ts imports — can read this key without pulling that stack back into
// its own dependency chain: authTeardown → backfill → conversationSync →
// apiClient → firebase → authTeardown would be a real import cycle.
export const POST_HISTORY_KEY = 'omi.syncBackfillPosts'
