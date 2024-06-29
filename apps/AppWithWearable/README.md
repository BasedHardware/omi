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

#### Automatic Setup

For your convenience, we have provided an `initialsetup.bash` script that automates the setup process. To use the script:

1. **Run the setup script**:
   In the terminal, navigate to the root directory of the project and run the `initialsetup.bash` script:
    ```
    bash ./apps/AppWithWearable/initialsetup.bash
    ```
   The script will guide you through the setup process, including upgrading Flutter, getting dependencies, installing iOS pods, creating the `.env` file, and running the Build Runner.

2. **Run the App**:
    - Select your target device in Xcode or Android Studio.
    - Run the app.

#### Manual Setup

If you prefer to set up the project manually, follow these steps:

1. **Upgrade Flutter**:
   Before proceeding, make sure your Flutter SDK is up to date:
    ```
    flutter upgrade
    ```

2. **Get Flutter Dependencies**:
   From within `apps/AppWithWearable`, install flutter packages:
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
    cat .env.template > .env
    ```

5. **API Keys**:
   Add your API keys to the `.env` file. (Sentry is not needed)

6. **Run Build Runner**:
   Generate necessary files with Build Runner:
    ```
    dart run build_runner build
    ```

7. **Run the App**:
    And select the target device when prompted 
    ```
    flutter run -t lib/main_prod.dart --flavor prod
    ```

This guide should help you get started with running the Friend App on your local machine. Make sure each step is completed to avoid any issues.