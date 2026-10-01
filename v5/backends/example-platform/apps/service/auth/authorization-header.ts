/**
 * Parse an `Authorization: Bearer <token>` header value. Returns null when the
 * header is absent, not a string, not Bearer-schemed, or carries an empty token.
 * Extracts a bearer token without revealing which part of the header was wrong.
 * Shared by the route modules; per-route request grammar stays per-route.
 */
export const bearerToken = (header: string | undefined): string | null => {
  if (typeof header !== "string" || !header.startsWith("Bearer ")) return null;
  const token = header.slice("Bearer ".length);
  return token.length > 0 ? token : null;
};
