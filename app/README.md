## Friend App

Check out https://docs.basedhardware.com/get_started/Setup/ for a guide on how to set up the app.

dart run build_runner build --delete-conflicting-outputs
flutter run --flavor dev -t lib/main.dart
flutter run --flavor dev -t lib/main.dart --release
flutter build apk -t lib/main.dart --release --flavor dev
flutter build apk -t lib/main.dart --release --flavor prod
flutter build appbundle -t lib/main.dart --release --flavor prod
export PATH="$PATH:/Volumes/Piyush/SDK/flutter/bin"

cd functions
firebase deploy --only functions

keytool -list -v -keystore /Volumes/Data/flutter_projects/Omi/app/android/Luca -alias Luca -storepass Luca@85730 -keypass Luca@85730



: CustomerInfo(entitlements: EntitlementInfos(all: {}, active: {}, verification: VerificationResult.notRequested), allPurchaseDates: {com.luca.plugin.eva:baseplan-eva: 2024-10-08T11:46:07.000Z}, activeSubscriptions: [com.luca.plugin.eva:baseplan-eva], allPurchasedProductIdentifiers: [com.luca.plugin.eva:baseplan-eva], nonSubscriptionTransactions: [], firstSeen: 2024-10-08T09:57:14.000Z, originalAppUserId: $RCAnonymousID:bc8d149dd1674555a7a9a19dbcd82fa3, allExpirationDates: {com.luca.plugin.eva:baseplan-eva: 2024-10-08T11:50:43.000Z}, requestDate: 2024-10-08T11:46:17.697Z, latestExpirationDate: 2024-10-08T11:50:43.000Z, originalPurchaseDate: null, originalApplicationVersion: null, managementURL: https://play.google.com/store/account/subscriptions)

Saving token gbgjhedcpdognejfjkjecfii.AO-J1Ozt4r9pt30YRHwO82WN-1isAC9iW3FG7J2oQGZ8zMfde16bmhvgD2LTfj7Lvb1rPZaUsy-kbnZqKL90D8gUiM-6uN9E-Q with hash vdlHS+wFPbjIB4iOXo/Wnpc0TlE=
