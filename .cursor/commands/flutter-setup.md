# Flutter Setup

Guide for setting up the Omi Flutter app development environment.

## Purpose

Set up the Flutter app for development on iOS, Android, macOS, or Windows.

## Prerequisites

- Flutter SDK (3.35.3 recommended)
- Xcode (for iOS/macOS)
- Android Studio (for Android)
- CocoaPods (for iOS)

## Automatic Setup (Recommended)

```bash
cd app
bash setup.sh ios     # or android, macos
```

This sets up the app to use Omi's development backend automatically.

## Manual Setup

1. **Verify Flutter installation**
   ```bash
   flutter doctor -v
   ```

2. **Get dependencies**
   ```bash
   cd app
   flutter pub get
   ```

3. **Install iOS pods**
   ```bash
   cd ios
   pod install
   pod repo update
   ```

4. **Configure environment**
   ```bash
   cd ..
   cat .env.template > .dev.env
   ```

5. **Add API keys to `.dev.env`**
   - `API_BASE_URL=https://api.omiapi.com/` (or your backend URL)
   - `OPENAI_API_KEY` (optional)
   - `GOOGLE_MAPS_API_KEY` (optional)

6. **Run build runner**
   ```bash
   dart pub run build_runner clean
   dart pub run build_runner build
   ```

7. **Set up Firebase**
   ```bash
   flutterfire config --out=lib/firebase_options_dev.dart ...
   ```

8. **Run the app**
   ```bash
   flutter run --flavor dev
   ```

## Platform-Specific Setup

### iOS
- Open `app/ios` in Xcode
- Configure signing
- Run from Xcode or `flutter run --flavor dev`

### Android
- Open `app/android` in Android Studio
- Configure signing
- Run from Android Studio or `flutter run --flavor dev`

## Troubleshooting

- **Flutter doctor issues**: Follow suggestions to fix
- **iOS build fails**: Run `pod install` in `ios/` directory
- **Android build fails**: Check NDK installation, accept licenses
- **Firebase auth issues**: Enable sign-in methods in Firebase Console

## Related Documentation

- App Setup: `docs/doc/developer/AppSetup.mdx`
- Flutter Architecture: `.cursor/rules/flutter-architecture.mdc`
