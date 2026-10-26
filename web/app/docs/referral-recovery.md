# Referral activation recovery

Google/Apple sign-in remains owned by AuthProvider and the Firebase auth-helper
work in PR #21355. LoginClient claims a referral only after the subscriber
publishes a user, scoped to that UID, referral code, environment and mounted
page. An account or route change cannot dispatch a late claim or redirect from
an older result. A failed claim has a real manual retry, without an automatic
request loop; eligibility/terminal rejections keep the existing continuation.

`claimReferralTrial` applies one 15-second deadline across token lookup, POST and
response decoding. It aborts the HTTP request and blocks dispatch from a token
lookup that returns after expiry. A committed server grant may still be observed
on a later retry; the client never manufactures a trial or changes entitlement.
The existing backend uses the referral grant transaction as authority.

These post-auth recovery changes preserve Firebase's existing auth domain and
callback configuration; they can merge independently of #21355. That separate
PR's auth-domain change and same-origin helper proxy must ship together, after
verifying authorized-domain coverage, the exact Google redirect URI and Apple's
Service ID return URL from its firebase-auth.md. Provider-connected sign-in,
referral return, destination preservation and cancellation still need integration
verification for that change and the complete incident outcome. A browser or
simulator is sufficient; the reporter's Samsung result is release/customer
follow-up, not an extra hardware merge gate. Do not claim the customer's
unspecified Try Again screen is fixed without identifying/verifying it.

Tests: referrals.test.ts and LoginClient.test.ts cover stalled token/network
operations, malformed replies, manual retry and a changed account.
