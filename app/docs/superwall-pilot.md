# Superwall paywall pilot

Upgrade entry points (end of onboarding, locked conversations and memories, chat quota, Settings, Usage) show a **Superwall** paywall on **iOS debug builds**, using the pilot's own Superwall test project (public SDK key built in as the default). Store builds and Android always use Omi's existing plans sheet and Stripe checkout. Pass `--dart-define=SUPERWALL_TEST_MODE=false` to see the plans sheet in debug, or `--dart-define=SUPERWALL_API_KEY_IOS=<key>` to point at another project.

## Before production

- Omi sets up its own Superwall project (paywall design, campaigns for the placements below) and replaces the test key.
- The plans are created as in-app purchase subscriptions in **App Store Connect** and attached to the paywall's product slots (the test project uses mock products, so prices show blank).
- Purchases must be reconciled to Omi subscriptions on the backend (Superwall webhooks or StoreKit server notifications), with restore and manage-subscription paths, before the pilot gate is removed.

## Dashboard setup

1. Use the public iOS SDK key from the Superwall project's Settings → API Keys. Never use a webhook secret or store private key in a `--dart-define` or commit it.
2. Attach the Calorie Tracker (Template) paywall to an isolated campaign for placement `omi_usage_upgrade_test`. Its sample purchase buttons are only for visual testing until sandbox products are configured.
3. Run the app in the dev flavor with the local profile. Example for iOS:

   ```sh
   flutter run --flavor dev --dart-define=OMI_APP_PROFILE=local_dev --dart-define=SUPERWALL_TEST_MODE=true --dart-define=SUPERWALL_API_KEY_IOS=YOUR_PUBLIC_TEST_KEY
   ```

   The current app setup and local auth emulator must also be running; see `app/AGENTS.md` and `app/setup.sh`.

4. Sign in, open Settings → Usage, and tap Upgrade. The pilot identifies the signed-in Firebase UID before registering the placement. Signing out resets the Superwall identity.

## Boundaries

- A configured paywall can offer a store purchase. Use sandbox/test store products and accounts only. This branch does not ingest Superwall purchase webhooks, reconcile App Store/Play purchases to Omi subscriptions, or grant Omi entitlements. A successful store purchase must not be treated as a successful Omi subscription until that backend path exists.
- The app's iOS deployment target (15) meets the SDK's documented minimum.
- Before a production rollout, decide the billing/catalog policy, add verified purchase lifecycle handling, reconcile Omi UID with Superwall's original user ID, add restore/manage behavior, and run store sandbox purchase and entitlement tests on devices.
