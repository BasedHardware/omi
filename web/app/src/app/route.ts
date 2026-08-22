/**
 * `/` sends signed-out visitors to the sign-in page.
 *
 * A route handler rather than a page: this only ever emits a redirect, so it
 * needs no React, no layout, and no client bundle. It was a page calling
 * `redirect()`, which made the root the one server-rendered route in the app —
 * and server rendering pulls in `src/app/layout.tsx`, which the build does not
 * bundle. In a deployed image, where the source tree is not shipped, that made
 * `/` the only route returning 500 while every client-shell route was fine.
 */
export function GET(request: Request): Response {
  return new Response(null, {
    status: 302,
    headers: { location: new URL('/login', request.url).toString() },
  });
}
