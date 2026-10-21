/**
 * Builds the Omi integrations endpoint for storing user memories.
 * Both segments are caller/env-controlled, so each is percent-encoded:
 * a uid containing `&` or `#` would otherwise corrupt the query string.
 */
export function integrationMemoriesUrl(appId, uid) {
  return `https://api.omi.me/v2/integrations/${encodeURIComponent(
    appId,
  )}/user/memories?uid=${encodeURIComponent(uid)}`;
}
