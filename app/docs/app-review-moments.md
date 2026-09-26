# Mobile store review moments

The iOS and Android app requests a native store review after a reader finishes a
useful surface. It never asks whether they like Omi first, requests a particular
score, offers a reward, or sends them to the store automatically. Store UI can
silently decline to appear. Returning from the API proves neither display nor a
rating; the app never stores a `hasRated` claim.

## Shipped policy

- Recap: a loaded, nonempty daily summary. The first recap a person reads can
  qualify once the familiarity gate below is satisfied.
- Conversation: the completed, non-discarded conversation's nonempty summary
  tab, outside onboarding. Opening a list, producing a first recording, or
  checking a task no longer prompts.
- Both require 15 seconds of visible, foreground, idle reading and a two-second
  pause at the bottom. A short page that fits can qualify after reading; a
  scrollable page requires a user scroll. These are timing proxies for having
  received value, not a measurement of happiness or content sentiment.
- Familiarity: at least three distinct local reading days and seven elapsed
  days since reading was first observed by this policy. There is no historical
  backfill or assumption that an old account has used the mobile app actively.
- One shared local budget: at least 120 days between native request attempts,
  at most three in a rolling 365 days, and once per marketing version. One
  availability/request attempt per process prevents retrying an unavailable
  store on every screen. Native quotas apply independently.
- Reserve the budget persistently before invoking the native API. A thrown
  native call still consumes it. Malformed state and persistence errors fail
  closed. Existing legacy prompt flags start a conservative 120-day cooldown
  on migration because their actual prompt date was never recorded.
- Cancel pending work on navigation, backgrounding, tab changes, editing,
  sharing, or other interruptions. Recheck immediately before the native call.
  Suppress during onboarding, signed-out state, calls and phone recording.
  Passive wearable capture does not prevent an otherwise quiet reading moment.
- Audio playback or seeking ends conversation review eligibility for that
  visit, including actions invoked through accessibility or transcript links.

The budget is installation-local, shared across both surfaces and local account
switches; it is not cross-device account state. Clearing application storage or
reinstalling can reset it. Store-side limits remain in force. No transcript,
summary text, sentiment, support history, payment status or feedback score is
used to select who gets asked. A user's private feedback never controls access
to the public review flow.

## Evidence and limits (2026-09-22)

The previous `AppReviewService` had separate first-conversation and first-task
flags, a custom blocking dialog, and external store navigation. Its global
`has_shown_review_prompt` flag was written but not used as a gate.

The existing telemetry identifies recap-card clicks, daily-summary detail
views, conversation-list/search clicks, app sessions, and account age. A single
recap open can emit `Daily Summary Detail Viewed` from both home and detail;
raw counts are not unique completed reads. There was no scroll-completion
emission. The task paths can report completion without honoring their save
result, so they are unsuitable review triggers in this change.

The source audit informed trigger selection; live aggregate results were not
available in the current environment. The analytics API credential was absent
and browser sign-in did not reach the existing project. No aggregate uplift,
retention effect or optimal threshold is claimed. The values above are
conservative product defaults to validate after release.

## Measurement

New events distinguish a reading opportunity, an attempted native request, and
the API returning/throwing. They include only closed moment/decision/result
values. They do not include content or identifiers, and use the existing
analytics consent, provenance and delivery path. No event is called “shown”,
“rated”, or “review completed”.

Compare opportunity eligibility and API errors by `moment`, platform, app
namespace and build. Use store-console rating volume/distribution as aggregate
outcomes; neither store permits reliable attribution of individual ratings to
these events. Watch subsequent engagement, exits and support complaints for
interruption harm. Do not optimize solely for five-star share. The checked-in
consumer query verifies instrumentation presence, not a deployed dashboard or
causal experiment. If later running a holdout, randomize before opportunity
selection, keep the same hard frequency limits, and assess retention alongside
aggregate ratings. Do not gate the review request on survey answers.

## Verification

Hermetic policy/service tests cover frequency boundaries, legacy migration,
concurrency, unavailable stores, native exceptions and persistence failures.
Reading-widget tests cover actual scrolling, reading time, short content,
background/route transitions, disabled tabs, identity replacement and disposal.
The shared adapter tests exercise the reading gate and service together.

Native display needs separate store-distributed testing: TestFlight does not
show StoreKit review prompts. On Android use a Play internal-test installation
and the appropriate tester account; a local APK/fake manager cannot prove a
production review was shown. No test or API return should be reported as a
submitted review.

## Platform references

- [Apple: requesting reviews](https://developer.apple.com/documentation/storekit/requesting-app-store-reviews)
- [Apple: ratings and reviews UX](https://developer.apple.com/design/human-interface-guidelines/ratings-and-reviews)
- [Google: in-app review timing, design and quotas](https://developer.android.com/guide/playcore/in-app-review)
- [Google: testing](https://developer.android.com/guide/playcore/in-app-review/test)
