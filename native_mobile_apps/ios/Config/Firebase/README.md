# Firebase client config

Public client identifiers (no credentials), copied from upstream `app/setup/release-firebase/`
and `app/setup/prebuilt/`. The "Copy Firebase config" build phase puts the one named by
`OMI_FIREBASE_PLIST` (a path) into the app as `GoogleService-Info.plist`:

| Config | Plist | Backend |
|---|---|---|
| Debug | `GoogleService-Info-Local.plist` (`demo-omi-local`, Auth emulator) | local harness |
| Release | `OMI_FIREBASE_PROD_PLIST`: inside the Omi repository `app/setup/release-firebase/GoogleService-Info.prod.plist`, in a separate checkout a copy set in `Secrets.xcconfig` (`based-hardware`) | `api.omi.me` |
