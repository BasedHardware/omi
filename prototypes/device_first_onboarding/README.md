# Device-first onboarding: design prototype

A clickable Flutter prototype of a new first-run flow for the Omi app, in two
visual directions (**Graphite** and **Aurora**). It is a design proposal for
review, not production code: it lives outside `app/` and depends only on
Flutter, so it runs without Firebase, the backend or app flavors.

Figma: "Omi — Paywall Redesign", pages **E · Device-first · Graphite** and
**F · Device-first · Aurora**.

## Run it

```bash
cd prototypes/device_first_onboarding
flutter create --platforms=ios,android,web .   # once: generates the platform folders (git-ignored)
flutter run                                    # or: flutter run -d chrome
```

The launcher lets you pick a direction and a trial length, then play the whole
flow or jump to any screen.

```bash
flutter test --exclude-tags screenshots                 # behaviour tests
flutter test --tags screenshots --update-goldens        # renders every screen to test/goldens/
```

## The flow

```
Everyone        Welcome → Sign in → Data & Privacy → Do you have your Omi?
Yes             Find Omi → Found → Paired → Name → Language → Permissions
                → Voice intro → Setting up → Your Omi is ready
                → Soft paywall (3 / 7 / 14 / 30-day trial) → Trial started → Home
It's on the way Waiting room → delivery push → Find Omi → …
No              Get your Omi ($129) → Order summary → Waiting room → …
```

- **The pendant is required.** The device question comes right after sign-in,
  before the user spends time on setup they can't use. Without a paired Omi
  there is no path to the paywall or home; users without one are sent to buy it
  and wait in a waiting room that only leads to pairing.
- **Soft paywall.** Pricing first appears at the end of onboarding, with
  "Continue with Free" always visible. A paired Omi works on Free (300 cloud
  minutes a month, then on-device).
- **Trial-length test.** The paywall's four arms differ only in trial length;
  headline, button, caption and reminder day follow from it (`TrialLength` in
  `lib/src/content.dart`). Judge the arms on trial-to-paid conversion and
  revenue per user who saw the paywall, not on trial starts.

## What is real and what is stubbed

| Area | In the prototype | In the app |
|---|---|---|
| Sign in, Data & Privacy | Stand-ins with today's copy | `auth.dart`, `ai_consent_widget.dart` |
| Find / pair Omi | Fake scan that "finds" the device after 3 s; copy from `find_device` | BLE scan and pairing |
| Name, language, permissions, voice | Same steps and copy as today's onboarding | Existing onboarding pages |
| Paywall plans | Static prices | Plan catalog + Stripe; needs a free trial (`trial_period_days` or an App Store / Play intro offer) |
| Buy Omi / checkout | Static order summary | Physical goods can't use In-App Purchase: Apple Pay / Shop Pay via the store |
| Waiting room, delivery push | Static order status | Store order status + a "delivered" webhook |
| Product imagery | The pendant is drawn in code (no assets) | Real product photography |

Values marked `Placeholder:` still need a decision: the monthly price, shipping
price and delivery window, the order data, and a real App Store review.

## Moving a direction into the app

Everything visual reads from `DfTheme` (`lib/src/theme.dart`), so adopting a
direction means mapping its tokens onto `OmiColors` / `OmiType` / `OmiRadius`,
moving copy into ARB files with `app/scripts/l10n.py`, and swapping the stubbed
screens for the existing onboarding pages. The mobile UX contract
(`app/docs/ux-contract.md`) applies once the code moves under `app/lib/`.
