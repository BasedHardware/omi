# App Detail Architecture

This package owns the mobile marketplace app-detail flow.

## Owners

- `app_detail.dart`: app lifecycle, install/enable state, subscription actions, and page composition.
- `app_summary.dart`: responsive app identity, rating, install count, and action presentation.
- `reviews_section.dart`: rating summary plus create/edit/review presentation.
- `reviews_list_page.dart`: the full reviews list.
- `widgets/`: reusable presentation components with no page lifecycle ownership.

Keep backend mutations in the owning page or section and pass refreshed state through callbacks. Do not duplicate install, subscription, or review mutation flows in widgets. Prefer a new focused file when a distinct section would otherwise make `app_detail.dart` grow.

## Verification

Run the app-detail and review widget tests, then `bash test.sh`. Exercise `app/e2e/flows/app-detail.yaml` on iOS and verify opening an app, returning to the marketplace, and the disabled/error path.

## Browser authorization and completion

`app_setup_owner.dart` is part of the same app-detail State library. It owns
bounded detail/setup reads, their identity/generation fences and the completion
wait. It calls the page's existing install owner only after a successful setup
verdict following an explicit user action. Setup failure is distinct from pending
and a missing endpoint; neither browser launch nor an absent endpoint claims a
connection. The shared `ConnectionWait` never overlaps probes and owns cancellation.
Initial metadata resolves before opening an app home, so a cached URL is not used
while a newer server URL is available. Home/settings use the system browser.
