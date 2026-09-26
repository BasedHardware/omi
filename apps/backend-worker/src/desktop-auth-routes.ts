// Desktop sign-in handoff routes, ported from the v4 worker (glue.rs Phase 2):
// start (native client), complete (confirmation page, Bearer Firebase ID
// token), exchange (native polling). Also serves the confirmation page the
// browser leg runs on. These routes are mounted WITHOUT authorizeV1 — the
// handoff is how a caller EARNS Firebase credentials; it cannot require them.
// Refusal bodies are v4-shaped {"error": "<message>"} because the only
// client is our own native module and page, which match on status codes.

import {
  DESKTOP_AUTH_CONFIRMATION_ATTEMPT_LIMIT,
  DESKTOP_AUTH_LIFETIME_MS,
  DESKTOP_AUTH_START_RATE_LIMIT,
  DESKTOP_AUTH_START_RATE_WINDOW_MS,
  browserUrlFor,
  createFirebaseCustomToken,
  deriveSessionId,
  isValidConfirmationCode,
  isValidSessionValue,
  verifierChallenge,
} from "./desktop-auth";
import {
  firebaseLocalId,
  readBoundedJson,
  type CoreContext,
  type CoreRoute,
} from "./http-core";
import { json } from "./wire";

function handoffError(message: string, status: number): Response {
  return json({ error: message }, status);
}

function sessionValue(body: unknown, key: string): string | null {
  if (body === null || typeof body !== "object" || Array.isArray(body))
    return null;
  const raw = (body as Record<string, unknown>)[key];
  return typeof raw === "string" && isValidSessionValue(raw) ? raw : null;
}

export async function handleDesktopAuthStart(
  context: CoreContext
): Promise<Response> {
  const db = context.env.DB;
  if (db === undefined) return handoffError("Desktop handoff unavailable", 503);
  const parsed = await readBoundedJson(context.req.raw, 4096);
  if (parsed.kind !== "ok") return handoffError("Invalid handoff", 400);
  const challenge = sessionValue(parsed.value, "challenge");
  const confirmationChallenge = sessionValue(
    parsed.value,
    "confirmationChallenge"
  );
  const sessionId = sessionValue(parsed.value, "sessionId");
  if (
    challenge === null ||
    confirmationChallenge === null ||
    sessionId === null
  )
    return handoffError("Invalid handoff", 400);
  if ((await deriveSessionId(challenge, confirmationChallenge)) !== sessionId)
    return handoffError("Invalid handoff", 400);
  const origin = new URL(context.req.url).origin;
  const browserUrl = browserUrlFor(origin, sessionId);
  if (browserUrl === null) return handoffError("Invalid handoff", 400);
  const now = Date.now();
  const clientIp = context.req.header("cf-connecting-ip") ?? "unknown";
  await db
    .prepare(
      "DELETE FROM desktop_auth_sessions WHERE expires_at <= ?1 OR consumed_at IS NOT NULL"
    )
    .bind(now)
    .run();
  const recent = await db
    .prepare(
      "SELECT COUNT(*) AS count FROM desktop_auth_sessions WHERE client_ip = ?1 AND created_at > ?2"
    )
    .bind(clientIp, now - DESKTOP_AUTH_START_RATE_WINDOW_MS)
    .first<{ count: number }>();
  if ((recent?.count ?? 0) >= DESKTOP_AUTH_START_RATE_LIMIT)
    return handoffError("Too many handoffs", 429);
  try {
    await db
      .prepare(
        "INSERT INTO desktop_auth_sessions (id, verifier_challenge, confirmation_challenge, client_ip, created_at, expires_at) VALUES (?1, ?2, ?3, ?4, ?5, ?6)"
      )
      .bind(
        sessionId,
        challenge,
        confirmationChallenge,
        clientIp,
        now,
        now + DESKTOP_AUTH_LIFETIME_MS
      )
      .run();
  } catch {
    return handoffError("Handoff already exists", 409);
  }
  return json({ browserUrl, expiresAt: now + DESKTOP_AUTH_LIFETIME_MS }, 201);
}

export async function handleDesktopAuthComplete(
  context: CoreContext
): Promise<Response> {
  const db = context.env.DB;
  const apiKey = context.env.FIREBASE_DESKTOP_API_KEY;
  if (db === undefined || typeof apiKey !== "string" || apiKey.length === 0)
    return handoffError("Authentication required", 401);
  const parsed = await readBoundedJson(context.req.raw, 4096);
  if (parsed.kind !== "ok") return handoffError("Authentication required", 401);
  const sessionId = sessionValue(parsed.value, "sessionId");
  const confirmationCode =
    parsed.kind === "ok" &&
    typeof (parsed.value as Record<string, unknown> | null)?.[
      "confirmationCode"
    ] === "string"
      ? ((parsed.value as Record<string, unknown>)[
          "confirmationCode"
        ] as string)
      : null;
  if (
    sessionId === null ||
    confirmationCode === null ||
    !isValidConfirmationCode(confirmationCode)
  )
    return handoffError("Authentication required", 401);
  const authorization = context.req.header("authorization");
  if (authorization === undefined || !authorization.startsWith("Bearer "))
    return handoffError("Authentication required", 401);
  const localId = await firebaseLocalId(
    authorization.slice("Bearer ".length),
    apiKey
  );
  if (localId === "unavailable")
    return handoffError("Authentication service unavailable", 503);
  if (localId === "invalid") return handoffError("Authentication failed", 401);
  // Atomic confirmation bind: the code check, attempt counting, and lockout
  // are one UPDATE so a wrong code cannot be retried concurrently past the
  // attempt limit.
  const now = Date.now();
  const bind = await db
    .prepare(
      `UPDATE desktop_auth_sessions
       SET uid = CASE WHEN confirmation_challenge = ?3 THEN ?1 ELSE uid END,
           confirmation_attempts = confirmation_attempts + CASE WHEN confirmation_challenge = ?3 THEN 0 ELSE 1 END,
           confirmation_locked_at = CASE
             WHEN confirmation_challenge != ?3 AND confirmation_attempts + 1 >= ${DESKTOP_AUTH_CONFIRMATION_ATTEMPT_LIMIT} THEN ?4
             ELSE confirmation_locked_at
           END
       WHERE id = ?2 AND uid IS NULL AND consumed_at IS NULL AND expires_at > ?4
         AND confirmation_locked_at IS NULL AND confirmation_attempts < ${DESKTOP_AUTH_CONFIRMATION_ATTEMPT_LIMIT}
       RETURNING uid, confirmation_attempts, confirmation_locked_at`
    )
    .bind(localId, sessionId, await verifierChallenge(confirmationCode), now)
    .first<{ uid: string | null }>();
  if (bind === null || bind.uid !== localId)
    return handoffError("Handoff expired or already completed", 409);
  return json({ completed: true });
}

export async function handleDesktopAuthExchange(
  context: CoreContext
): Promise<Response> {
  const db = context.env.DB;
  if (db === undefined) return handoffError("Desktop handoff unavailable", 503);
  const parsed = await readBoundedJson(context.req.raw, 4096);
  if (parsed.kind !== "ok") return handoffError("Invalid handoff", 400);
  const sessionId = sessionValue(parsed.value, "sessionId");
  const verifier = sessionValue(parsed.value, "verifier");
  if (sessionId === null || verifier === null)
    return handoffError("Invalid handoff", 400);
  const serviceAccountEmail = context.env.FIREBASE_DESKTOP_TOKEN_SA_EMAIL;
  const privateKey = context.env.FIREBASE_DESKTOP_TOKEN_PRIVATE_KEY;
  if (
    typeof serviceAccountEmail !== "string" ||
    serviceAccountEmail.length === 0 ||
    typeof privateKey !== "string" ||
    privateKey.length === 0
  )
    return handoffError("Desktop token signing unavailable", 503);
  const now = Date.now();
  const row = await db
    .prepare(
      "SELECT uid FROM desktop_auth_sessions WHERE id = ?1 AND verifier_challenge = ?2 AND consumed_at IS NULL AND expires_at > ?3"
    )
    .bind(sessionId, await verifierChallenge(verifier), now)
    .first<{ uid: string | null }>();
  if (row === null) return handoffError("Handoff expired", 410);
  if (row.uid === null) return json({ status: "pending" }, 409);
  const customToken = await createFirebaseCustomToken(
    row.uid,
    serviceAccountEmail,
    privateKey,
    Math.floor(now / 1000)
  );
  if (customToken === null)
    return handoffError("Desktop token signing unavailable", 503);
  const consumed = await db
    .prepare(
      "UPDATE desktop_auth_sessions SET consumed_at = ?1 WHERE id = ?2 AND consumed_at IS NULL"
    )
    .bind(now, sessionId)
    .run();
  if ((consumed.meta.changes ?? 0) !== 1)
    return handoffError("Handoff already consumed", 409);
  return json({ customToken });
}

export function handleDesktopAuthPage(context: CoreContext): Response {
  const apiKey = context.env.FIREBASE_DESKTOP_API_KEY;
  if (typeof apiKey !== "string" || apiKey.length === 0)
    return handoffError("Desktop handoff unavailable", 503);
  const query = new URL(context.req.url).searchParams;
  if (
    [...query.keys()].some((key) => key !== "desktop_auth") ||
    query.getAll("desktop_auth").length > 1
  )
    return handoffError("Invalid handoff", 400);
  const sessionId = query.get("desktop_auth");
  if (sessionId === null || !isValidSessionValue(sessionId))
    return handoffError("Invalid handoff", 400);
  const config = JSON.stringify({
    apiKey,
    sessionId,
  }).replace(/</g, "\\u003c");
  return new Response(desktopAuthPageHtml(config), {
    status: 200,
    headers: {
      "content-type": "text/html; charset=utf-8",
      "cache-control": "no-store",
      "content-security-policy":
        "default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self' https://identitytoolkit.googleapis.com; form-action 'none'; base-uri 'none'; frame-ancestors 'none'",
      "referrer-policy": "no-referrer",
    },
  });
}

function desktopAuthPageHtml(configJson: string): string {
  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Omi development sign-in</title>
<style>
  :root { color-scheme: light dark; }
  body { margin: 0; min-height: 100vh; display: flex; align-items: center; justify-content: center;
         font: 15px/1.5 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
         background: #f5f4f1; color: #1d1d1f; }
  @media (prefers-color-scheme: dark) { body { background: #161618; color: #f5f5f7; } }
  main { width: 100%; max-width: 380px; margin: 32px; padding: 28px; border-radius: 18px;
         background: rgba(255,255,255,0.72); box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
  @media (prefers-color-scheme: dark) { main { background: rgba(38,38,42,0.72); } }
  h1 { font-size: 20px; margin: 0 0 6px; }
  p { margin: 0 0 14px; color: #6e6e73; font-size: 13px; }
  label { display: block; font-size: 12px; margin: 12px 0 4px; color: #6e6e73; }
  input { width: 100%; box-sizing: border-box; padding: 10px 12px; border-radius: 10px;
          border: 1px solid #d2d2d7; font-size: 15px; background: transparent; color: inherit; }
  input:focus { outline: 2px solid #0071e3; outline-offset: -1px; }
  input[code] { text-align: center; letter-spacing: 8px; font-variant-numeric: tabular-nums; }
  button { width: 100%; margin-top: 16px; padding: 11px 16px; border: 0; border-radius: 12px;
           background: #1d1d1f; color: #fff; font-size: 15px; cursor: pointer; }
  @media (prefers-color-scheme: dark) { button { background: #f5f5f7; color: #1d1d1f; } }
  button[secondary] { background: transparent; border: 1px solid #d2d2d7; color: inherit; }
  button:disabled { opacity: 0.5; cursor: default; }
  .error { color: #a0392e; font-size: 13px; margin-top: 10px; min-height: 18px; }
  .done { text-align: center; padding: 12px 0 4px; }
  .toggle { margin-top: 14px; text-align: center; font-size: 13px; color: #6e6e73; }
  .toggle button { all: unset; cursor: pointer; color: #0071e3; }
</style>
</head>
<body>
<main id="app"></main>
<script>
"use strict";
var CONFIG = ${configJson};
var app = document.getElementById("app");
var state = { idToken: null };

function el(html) {
  var template = document.createElement("template");
  template.innerHTML = html.trim();
  return template.content.firstChild;
}

function showCredentials() {
  var signUp = false;
  function render(message) {
    var view = el(
      '<form id="form">' +
      "<h1>Omi development sign-in</h1>" +
      "<p>Development build. Sign in with a development Omi account (email and password), then enter the code shown in the Omi app.</p>" +
      '<label for="email">Email</label><input id="email" type="email" autocomplete="email" required>' +
      '<label for="password">Password</label><input id="password" type="password" autocomplete="current-password" required>' +
      '<button id="submit" type="submit">Continue</button>' +
      '<div class="error" id="error"></div>' +
      '<div class="toggle"></div>' +
      "</form>"
    );
    app.replaceChildren(view);
    view.querySelector("#submit").textContent = signUp ? "Create account" : "Continue";
    view.querySelector(".toggle").appendChild(
      // el() returns firstChild, so the fragment must lead with an element —
      // a text-leading fragment would append only the text and drop the button.
      el(signUp
        ? '<span>Have an account? <button type="button">Sign in instead</button></span>'
        : '<span>No development account? <button type="button">Create one</button></span>')
    );
    view.querySelector(".toggle button").addEventListener("click", function () {
      signUp = !signUp;
      render();
    });
    if (message) view.querySelector("#error").textContent = message;
    view.addEventListener("submit", function (event) {
      event.preventDefault();
      var button = view.querySelector("#submit");
      button.disabled = true;
      var endpoint = signUp ? "accounts:signUp" : "accounts:signInWithPassword";
      fetch("https://identitytoolkit.googleapis.com/v1/" + endpoint + "?key=" + encodeURIComponent(CONFIG.apiKey), {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          email: view.querySelector("#email").value.trim(),
          password: view.querySelector("#password").value,
          returnSecureToken: true,
        }),
      })
        .then(function (response) {
          response.json().then(function (body) {
            if (!response.ok || !body.idToken) {
              button.disabled = false;
              render(firebaseError(body, signUp));
              return;
            }
            state.idToken = body.idToken;
            showCode();
          });
        })
        .catch(function () {
          button.disabled = false;
          render("Could not reach the sign-in service. Try again.");
        });
    });
  }
  render();
}

function firebaseError(body, signUp) {
  var message =
    body && body.error && typeof body.error.message === "string"
      ? body.error.message
      : "";
  if (message.indexOf("EMAIL_NOT_FOUND") === 0 || message.indexOf("INVALID_LOGIN_CREDENTIALS") === 0 || message.indexOf("INVALID_PASSWORD") === 0) {
    return "Email or password is incorrect.";
  }
  if (message.indexOf("EMAIL_EXISTS") === 0) {
    return "That email already has an account. Sign in instead.";
  }
  if (message.indexOf("WEAK_PASSWORD") === 0) {
    return "Choose a stronger password (at least 6 characters).";
  }
  if (message.indexOf("TOO_MANY_ATTEMPTS") === 0) {
    return "Too many attempts. Wait a moment and try again.";
  }
  return signUp ? "Could not create the account. Try again." : "Could not sign in. Try again.";
}

function showCode(message) {
  var view = el(
    '<form id="form">' +
    "<h1>Enter the code</h1>" +
    "<p>The Omi app is showing a 6-digit code. Type it below to finish signing in.</p>" +
    '<label for="code">6-digit code</label><input id="code" code inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="one-time-code" required autofocus>' +
    '<button id="submit" type="submit">Finish sign-in</button>' +
    '<div class="error" id="error"></div>' +
    "</form>"
  );
  app.replaceChildren(view);
  if (message) view.querySelector("#error").textContent = message;
  view.addEventListener("submit", function (event) {
    event.preventDefault();
    var button = view.querySelector("#submit");
    button.disabled = true;
    view.querySelector("#error").textContent = "";
    fetch("/v1/auth/desktop/complete", {
      method: "POST",
      headers: {
        "content-type": "application/json",
        authorization: "Bearer " + state.idToken,
      },
      body: JSON.stringify({
        sessionId: CONFIG.sessionId,
        confirmationCode: view.querySelector("#code").value.trim(),
      }),
    })
      .then(function (response) {
        if (response.ok) {
          showDone();
          return;
        }
        button.disabled = false;
        view.querySelector("#error").textContent =
          response.status === 409
            ? "That code is not right, or the handoff already finished. Check the code in the Omi app."
            : response.status === 401
            ? "Your sign-in expired. Reload this page and start again."
            : "Could not finish sign-in. Try again.";
      })
      .catch(function () {
        button.disabled = false;
        view.querySelector("#error").textContent = "Network problem. Try again.";
      });
  });
}

function showDone() {
  app.replaceChildren(
    el(
      '<div class="done">' +
      "<h1>You are signed in</h1>" +
      "<p>Return to the Omi app — it finishes on its own.</p>" +
      "</div>"
    )
  );
}

showCredentials();
</script>
</body>
</html>`;
}

export const desktopAuthRoutes: readonly CoreRoute[] = [
  {
    method: "POST",
    path: "/v1/auth/desktop/start",
    handle: handleDesktopAuthStart,
  },
  {
    method: "POST",
    path: "/v1/auth/desktop/complete",
    handle: handleDesktopAuthComplete,
  },
  {
    method: "POST",
    path: "/v1/auth/desktop/exchange",
    handle: handleDesktopAuthExchange,
  },
  { method: "GET", path: "/auth/desktop", handle: handleDesktopAuthPage },
];
