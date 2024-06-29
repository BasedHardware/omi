---
layout: default
title: Getting Started
nav_order: 1
---

# Getting Started

Follow these steps to get started with your Friend.

### Install the app

1. Clone the repo `git clone https://github.com/BasedHardware/friend.git`
3. Install [Flutter](https://docs.flutter.dev/get-started/install/macos/mobile-ios?tab=download) and [CocoaPods](https://guides.cocoapods.org/using/getting-started.html)
4. Install your environment variables for `apps/AppWithWearable`:
   - You can copy .env.template file as .env and add your keys to it
   - Or you can set the api keys needed on the mobile App from the settings page itself (enable Developer mode)
5. Build targets:
   - iOS: Download/install [XCode](https://apps.apple.com/us/app/xcode/id497799835?mt=12) then navigate to the iOS folder. You might need to launch Xcode to select a team and specify a bundle identifier.
   - Android: Download/install [Android Studio](https://developer.android.com/studio) then navigate to the Android folder.
6. Run `flutter clean ` then `flutter pub get` then `pod install`.
7. When everything is installed, run `flutter run `, this should run your app on the selected device (iOS or Android).

[Next Step: Buying Guide →](/assembly/Buying_Guide/){: .btn .btn-purple }
