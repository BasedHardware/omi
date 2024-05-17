## Friend App

This guide walks you through the steps required to run the app locally on your machine. Please
follow the instructions carefully to ensure a smooth setup.

### Prerequisites

Before starting, make sure you have the following installed:

- Flutter SDK
- Dart SDK
- Xcode (for iOS)
- Android Studio (for Android)
- CocoaPods (for iOS dependencies)

### Setup Instructions

1. **Get Flutter Dependencies**:
   From within `apps/AppStandalone`, install flutter packages:
    ```
    flutter pub get
    ```

2. **Install iOS Pods**:
   Navigate to the iOS directory and install the CocoaPods dependencies:
    ```
    cd ios
    pod install
    pod repo update
    ```

3. **Environment Configuration**:
   Rename the environment configuration file:
    ```
    cd ..
    mv .env.template .env
    ```

4. **API Keys**:
   Add your API keys to the `.env` file. (Sentry is not needed)

5. **Run Build Runner**:
   Generate necessary files with Build Runner:
    ```
    dart run build_runner build
    ```

6. **Run the App**:
    - Select your target device in Xcode or Android Studio.
    - Run the app.
