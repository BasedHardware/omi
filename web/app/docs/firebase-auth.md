# Firebase redirect sign-in deployment

The production browser uses `app.omi.me` as its Firebase auth domain when the
build config names a Firebase Hosting domain. The generated Bun server proxies
`/__/auth/*` and `/__/firebase/init.json` to the build's Firebase project Hosting
origin. The proxy module ships inside `.moonshine`, so the runtime image needs
no additional environment variables. Local and preview hosts retain their
configured auth domain.

This implements Firebase's [same-origin proxy guidance](https://firebase.google.com/docs/auth/web/redirect-best-practices#proxy-requests).
Safari blocks storage access to the old cross-origin helper iframe, which can
return from Google without a session or an SDK error. The helper must be proxied
transparently, rather than redirected to Firebase Hosting. App pages retain
`frame-ancestors 'none'`; the helper alone permits same-origin framing.

Before deploying, verify these console settings (code does not change them):

- Firebase Authentication authorized domains include `app.omi.me`.
- The project's Google OAuth web client permits the exact redirect URI
  `https://app.omi.me/__/auth/handler`.
- Apple's Service ID web configuration permits that return URL and domain too.
  Keep the existing Firebase Hosting return URI for other clients.

After deployment, verify `/__/auth/iframe` serves the Firebase helper with
`X-Frame-Options: SAMEORIGIN`, then test Google and Apple on iPhone Safari and
Google popup sign-in on desktop Chrome. Use the reported link:

```text
https://app.omi.me/login?next=%2Fitems%3Ftask%3D6zDh2tLd9O8JDbAVKezY%26task%3D3j79CowojdreNQv5k27J%26task%3D8fMv4K1jvc3eKsW4lVXF
```

The destination must retain all three `task` values. Also test a referral signup,
a cancelled sign-in, and an ordinary signed-out visit. Popup completion alone
must not navigate: the auth subscriber publishes the session before LoginClient
navigates, so ProtectedRoute cannot bounce a transient anonymous render back to
login. Mobile continues to use redirects, desktop continues to use popups.
