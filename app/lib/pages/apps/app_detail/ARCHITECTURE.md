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
