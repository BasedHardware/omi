# Onboarding, paywall & app: design prototype

A clickable Flutter prototype of a new first run and the main app for Omi. It
is a design proposal for review, not production code: it lives outside `app/`
and depends only on Flutter, so it runs without Firebase, the backend or app
flavors.

It holds two onboarding flows and the app they lead into:

- **Paywall first** (default, modelled on Pocket's onboarding): the paywall
  comes straight after sign-in, a one-time 30-day winback follows if it is
  closed, then a soft setup and pairing. In **Aurora Light**.
- **Device first (v1)**: pairing first, soft paywall at the end. In
  **Graphite** and **Aurora** (the earlier review round).
- **The app**: home, tasks, conversations, daily recaps, Ask Omi, search,
  settings, plan & usage, device, memories, integrations and recording, mirroring
  the screens in `app/lib` in the Aurora Light design language.

## Run it

```bash
cd prototypes/device_first_onboarding
flutter create --platforms=ios,android,web .   # once: generates the platform folders (git-ignored)
flutter run                                    # or: flutter run -d chrome
```

The launcher picks a flow, a look and a trial arm, then plays the flow or jumps
to any onboarding or app screen (as a Free or Unlimited user).

```bash
flutter test --exclude-tags screenshots                 # behaviour and overflow tests
flutter test --tags screenshots --update-goldens        # renders every screen to test/goldens/
```

## Paywall first

```
Welcome (sign in) → Paywall ──"Try for $0.00"──→ Pay via web (Stripe) ─┐
                     │      ──"Try with App Store"→ App Store sheet ───┤ trial
                     └ close → Winback: "upgraded to 30 days free" ────┤
                                  └ No thanks → (Free) ────────────────┤
Permissions (Bluetooth required) → "Let's get your Omi set up"  ←──────┘
  → Find → Found → Paired → Name → Voice → Setting up → Ready → App
No Omi ("Get one now" / "I don't have my Omi yet") → Buy → Order → Waiting room → Find …
```

- **Paywall before onboarding.** Users see the offer at peak intent, right
  after sign-in. The paywall explains the trial with a dated timeline (today,
  reminder, charge date) and a swipeable carousel of what Unlimited does.
- **Two ways to pay.** "Try for $0.00" opens web checkout (Stripe, Apple Pay or
  card; no App Store fee); "Try with App Store" uses In-App Purchase. Apple's
  rules on linking out to web checkout differ by storefront (the US allows it
  since the 2025 Epic ruling), so the web option should be gated by region.
- **Winback.** Closing the paywall shows a one-time offer that upgrades the
  trial to 30 days. Declining lands on Free; the paywall does not return during
  onboarding.
- **Pairing is still required.** Every path ends in pairing; users without an
  Omi are sent to buy one.
- **Trial-length test.** The first paywall's arms are 3, 7 and 14 days
  (`DfOffer.paywallFirstArms` in `lib/src/content.dart`); the winback is always
  30 days. Judge arms on trial-to-paid conversion and revenue per user who saw
  the paywall, not on trial starts.

In the app, Free users see their monthly minutes, conversations older than two
days are locked behind "Upgrade to Unlimited", and Plan & Usage previews the
paywall shown when the monthly cap is hit.

## Device first (v1)

```
Everyone        Welcome → Sign in → Data & Privacy → Do you have your Omi?
Yes             Find Omi → Found → Paired → Name → Language → Permissions
                → Voice intro → Setting up → Your Omi is ready
                → Soft paywall (3 / 7 / 14 / 30-day trial) → Trial started → Home
It's on the way Waiting room → delivery push → Find Omi → …
No              Get your Omi ($129) → Order summary → Waiting room → …
```

## What is real and what is stubbed

| Area | In the prototype | In the app |
|---|---|---|
| Sign in | Buttons that continue | `auth.dart` |
| Paywall, winback, checkout | Static prices and dated copy; checkout sheets are mock-ups | Plan catalog + Stripe Checkout / RevenueCat; needs a free trial (`trial_period_days` or an App Store / Play intro offer) and a winback offer |
| Find / pair Omi | Fake scan that "finds" the device after 3 s | BLE scan and pairing |
| Permissions | Bluetooth prompt is a stand-in dialog | System permission prompts |
| Buy Omi / checkout | Static order summary | Physical goods can't use In-App Purchase: Apple Pay / Shop Pay via the store |
| App screens | Sample conversations, tasks, memories and apps (`lib/src/app/mock_data.dart`); chat answers are canned | Backend data |
| Product imagery | The pendant is drawn in code (no assets) | Real product photography |

Values marked `Placeholder:` still need a decision: the monthly price, shipping
price and delivery window, the order data, and a real App Store review.
Headlines use Instrument Serif (SIL Open Font License, `fonts/OFL.txt`).

## Moving a direction into the app

Everything visual reads from `DfTheme` (`lib/src/theme.dart`), so adopting a
direction means mapping its tokens onto `OmiColors` / `OmiType` / `OmiRadius`,
moving copy into ARB files with `app/scripts/l10n.py`, and swapping the stubbed
screens for the existing pages. The mobile UX contract
(`app/docs/ux-contract.md`) applies once the code moves under `app/lib/`.
