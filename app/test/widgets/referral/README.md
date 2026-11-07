# Referral widget configurations

Use the repository-pinned Flutter 3.44.5 from `app/`:

```sh
flutter test test/widgets/referral/referral_page_test.dart
flutter test --dart-define=OMI_MOBILE_REFERRAL_CAMPAIGN=true test/widgets/referral/referral_page_test.dart
```

The default configuration exercises URL validation and the dormant gate; four
campaign widgets are explicitly skipped. The enabled configuration exercises URL
validation and all four campaign widgets; the dormant-gate test is explicitly
skipped. A skipped configuration is not a passing execution of those assertions.
Run both commands when changing this flow. Local MUX runs also follow its
resource preflight and build-slot guards.
