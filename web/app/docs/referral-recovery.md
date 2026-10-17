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

Deploy these client changes together with #21355's same-origin helper proxy.
Verify the Firebase authorized domain, exact Google redirect URI and Apple
Service ID return URL from that PR's firebase-auth.md before claiming completion.
A real Google return, referral result and cancellation on Samsung S26 Ultra
remain release acceptance checks. Do not claim the customer's unspecified
Try Again screen is fixed without identifying/verifying it.

Tests: referrals.test.ts and LoginClient.test.ts cover stalled token/network
operations, malformed replies, manual retry and a changed account.
