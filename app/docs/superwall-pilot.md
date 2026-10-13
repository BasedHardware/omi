# Local Superwall pilot

This branch adds a test placement to the Flutter Usage page. It leaves Omi's existing Stripe checkout in place. The pilot runs only on **iOS** in a **debug** build with the `local_dev` profile, `SUPERWALL_TEST_MODE=true`, and a public Superwall iOS SDK key. Without all of those, Upgrade opens the existing plans sheet.

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
