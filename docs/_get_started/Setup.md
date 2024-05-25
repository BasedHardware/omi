---
layout: default
title: Getting Started
nav_order: 1
---

# Getting Started

Follow these steps to get started with your Friend.

### Install the app

1. Clone the repo `git clone https://github.com/BasedHardware/friend.git`
2. Choose which version of the app you want to install (see Structure):
   - Don't have the device? Run `cd apps/AppStandalone` in terminal.
   - Have the device/NRF Board? Run `cd apps/AppWithWearable` in terminal.
3. Install [Flutter](https://docs.flutter.dev/get-started/install/macos/mobile-ios?tab=download) and [CocoaPods](https://guides.cocoapods.org/using/getting-started.html)
4. Install your environment variables:
   - For **AppStandalone**, update variables in in .env.template file
   - For **AppWithWearable**, you can set the api keys needed on the mobile App from the settings page itself
5. Build targets:
   - iOS: Download/install [XCode](https://apps.apple.com/us/app/xcode/id497799835?mt=12) then navigate to the iOS folder. You might need to launch Xcode to select a team and specify a bundle identifier.
   - Android: Download/install [Android Studio](https://developer.android.com/studio) then navigate to the Android folder.
   - Web/Simulator: Do not run in the web/simulator as Bluetooth will not work.
6. Run `flutter clean ` then `flutter pub get` then `pod install`.
7. When everything is installed, run `flutter run `, this should run your app on the selected device (iOS or Android).

[Next Step: Buying Guide →](https://basedhardware.github.io/Friend/assembly/Buying_Guide/){: .btn .btn-purple }
