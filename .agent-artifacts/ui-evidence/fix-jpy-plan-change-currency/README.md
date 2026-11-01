# Japanese JPY plan sheet verification

Production `PlansSheet`, generated `GeneratedAvailablePlansResponse` and providers,
with a synthetic existing Plus subscription and four injected JPY offers. The
amounts here are test values, not assertions about production prices. No real
account is signed in and the final payment confirmation is not submitted.

After `make lane-bootstrap`, from `app/`, run against an owned iOS simulator:

```sh
OMI_APP_PROFILE=local_dev flutter run --no-hot --debug --flavor dev \
  -d <owned-simulator-id> \
  -t ../.agent-artifacts/ui-evidence/fix-jpy-plan-change-currency/billing_currency.dart \
  --dart-define=OMI_APP_PROFILE=local_dev
```

Verified 2026-10-25 with Flutter 3.44.5 / Dart 3.12.2, Xcode iOS 26.5 simulator
on iPhone 16 Pro. The Flutter locale is Japanese. The native shell uses the
hermetic local development configuration. A fresh non-hot compilation was used
after an incremental hot restart exposed a stale helper signature; the final
run built successfully in 43.5 seconds.

Through `agent-flutter`, scroll the plan cards into view, select Unlimited,
check the annual whole-yen total, switch to Monthly and tap Continue. Confirm
that the dialog names the exact selected JPY offer. Tap Cancel and confirm the
sheet returns with the selection intact. The screenshots record those states.
The fixture has the same behavior as the captured entrypoint; hook formatting
only changes layout in this source file.

This is UI/consumer verification, not a native-to-Stripe payment test. The
separate opt-in integration test in
`backend/tests/integration/billing/test_jpy_plan_changes_stripe.py` exercises the
real FastAPI routes and Stripe sandbox payments/schedules/errors with synthetic
customers. Backend unit tests and Flutter widget tests cover the same wire and
selection boundaries hermetically. Production price/account configuration and
the released customer workflow remain separate release checks.
