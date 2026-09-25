# Release Firebase client config

These files are the Firebase **client** config that Codemagic release builds compile against:
`firebase_options_{prod,dev}.dart`, `google-services.{prod,dev}.json` and
`GoogleService-Info.{prod,dev}.plist`. They hold public identifiers (project id, app ids, the
Firebase-restricted client API keys) that every shipped APK and IPA already carries. They are
not credentials.

`scripts/install_release_firebase_config.sh` copies them to the paths the build reads
(`lib/`, `android/app/src/{prod,dev}/`, `ios/Config/{Prod,Dev}/`). Codemagic runs it instead
of `flutterfire config --service-account=...`, so release builds need no Google Cloud key.

## Refreshing

Refresh only when a Firebase app is added, removed or re-registered. Use your own Google login
(`gcloud auth application-default login` or `firebase login`), never a service-account key, and
run from a scratch copy of `app/` because `flutterfire config` also rewrites the Xcode project:

```bash
flutterfire config --platforms=android,ios --out=lib/firebase_options_prod.dart \
  --ios-bundle-id=com.friend-app-with-wearable.ios12 --android-package-name=com.friend.ios \
  --android-out=android/app/src/prod/ --ios-out=ios/Config/Prod/ \
  --project=based-hardware --ios-target=Runner --yes
flutterfire config --platforms=android,ios --out=lib/firebase_options_dev.dart \
  --ios-bundle-id=com.friend-app-with-wearable.ios12.development --android-package-name=com.friend.ios.dev \
  --android-out=android/app/src/dev/ --ios-out=ios/Config/Dev/ \
  --project=based-hardware-dev --ios-target=Runner --yes
```

Copy the six outputs back here under the names above and review the diff before committing.
