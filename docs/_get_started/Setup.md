---
layout: default
title: Getting Started
nav_order: 1
---

# Getting Started

Follow these steps to get started with your Friend.

### Install the app

1. Clone the repo `git clone https://github.com/BasedHardware/friend.git`
2. Choose which version of the app you want to install (see Structure).
   - Don't have the device? run `cd apps/AppStandalone` in terminal
   - Have the device/NRF Board? run `cd apps/AppWithWearable` in terminal
3. Install [Flutter](https://docs.flutter.dev/get-started/install/macos/mobile-ios?tab=download) and [CocoaPods](https://guides.cocoapods.org/using/getting-started.html)
4. Install your environment variables

   - For AppWithWearable, open file ble_receive_w_a_v.dart located in `apps/AppWithWearable/lib/custom_code/actions/` Find "DEEPGRAM_API_KEY" and provide your own api-key for Deepgram for transcriptions to work

      <img src="https://basedhardware.github.io/Friend/images/getting_started_snapshot_1.png" alt="getting_started_snapshot_1" width="400">

   then, go to apps/AppWithWearable/lib/custom_code/actions and in the "stream_api_response" file, add your openai key instead of "key"
   
   ![CleanShot 2024-04-11 at 00 17 32](https://github.com/BasedHardware/Friend/assets/43514161/c4d9a61d-df17-4dd5-912e-3e602fa5066c)

   - For AppStandalone, update variables in in .env.template file

6. iOS: [Install XCode](https://apps.apple.com/us/app/xcode/id497799835?mt=12) then navigate to the iOS folder. You might need to launch Xcode to select a team and specify a bundle identifier.
   Android: Download/install [android Studio ](https://developer.android.com/studio) then navigate to the Android folder
   Don't run in web/simulator: Bluetooth will not work
7. Run `flutter clean ` then `flutter pub get` then `pod install`
8. When everything is installed, run `flutter run `, this should run your app on a selected device


### No-Code Alternative:

- Don't have the device? [Clone this Flutterflow Project ](https://app.flutterflow.io/project/friend-0x9u40)
- Have the wearable device? [Copy this Flutterflow Project](https://app.flutterflow.io/project/friend-share-19bk3d)


[Next Step: Buying Guide →](https://basedhardware.github.io/Friend/assembly/Buying_Guide/){: .btn .btn-purple }
