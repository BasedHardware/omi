---
layout: default
title: App Setup
nav_order: 1
---

# App Setup 📱

Follow these steps to get started with your Friend. Don't want to bother with code? Use our official version
on [Apple](https://apps.apple.com/us/app/friend-ai-wearable/id6502156163)/[Google](https://play.google.com/store/apps/details?id=com.friend.ios&hl=en_US) store

### Install the app

Before starting, make sure you have the following installed:

- Flutter SDK
- Dart SDK
- Xcode (for iOS)
- Android Studio (for Android)
- CocoaPods (for iOS dependencies)
- NDK 26.3.11579264 or above (to build Opus for ARM Devices)

### Setup Instructions

1. **Upgrade Flutter**:
   Before proceeding, make sure your Flutter SDK is up to date:
    ```
    flutter upgrade
    ```

2. **Get Flutter Dependencies**:
   From within `app` directory, install flutter packages:
    ```
    flutter pub get
    ```

3. **Install iOS Pods**:
   Navigate to the iOS directory and install the CocoaPods dependencies:
    ```
    cd ios
    pod install
    pod repo update
    ```

4. **Environment Configuration**:
   Create `.env` using template `.env.template`
    ```
    cd ..
    cat .env.template > .dev.env
    ```

5. **API Keys**:
   Add your API keys to the `.env` file. (Sentry is not needed)

    - `API_BASE_URL` is your backend url. Follow this guide to [install backend](https://github.com/BasedHardware/Omi/tree/main/backend)

6. **Run Build Runner**:
   Generate necessary files with Build Runner:
    ```
    dart run build_runner build
    ```

7. **Setup Firebase**:
    - Follow official [Firebase Docs](https://firebase.google.com/docs/flutter/setup) till Step 1
    - Run the following command to register the prod flavor of the app. The command will prompt you to select `configuration type`; under it, select `Target` and then `Runner`

       ```
       flutterfire config --out=lib/firebase_options_prod.dart --ios-bundle-id=com.friend-app-with-wearable.ios12 --android-app-id=com.friend.ios --android-out=android/app/src/prod/  --ios-out=ios/Config/Prod/
       ```
    - Similarly for dev environment

       ```
       flutterfire config --out=lib/firebase_options_dev.dart --ios-bundle-id=com.friend-app-with-wearable.ios12.develop --android-app-id=com.friend.ios.dev --android-out=android/app/src/dev/  --ios-out=ios/Config/Dev/
       ```
    - Generate SHA1/SHA256 Keys for your Keystore and add them to Firebase. Follow the steps mentioned in this [StackOverflow answer](https://stackoverflow.com/a/56091158) or
      the [Official Docs](https://support.google.com/firebase/answer/9137403?hl=en). This is required for Firebase Auth through Google OAuth to work.

   If you're facing auth issues running the app, enable Google/Apple sign-in in Firebase. Go to the Firebase console and select your project. In the left-hand menu, click on "Authentication." On the "Sign-in method" tab, scroll down to the "Sign-in providers" section. Click on the "Google" sign-in provider. Click the "Enable" switch to enable Google Sign-In for your Firebase project.

8. **Run the App**:
    - Select your target device in Xcode or Android Studio.
    - Run the app.

Having troubles? [Join Discord and search your issue in help channel](https://discord.gg/based-hardware-1192313062041067520)

[Next Step: Buying Guide →](/assembly/Buying_Guide/){: .btn .btn-purple }
