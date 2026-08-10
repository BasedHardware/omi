# Omi App

The Omi App is a Flutter-based mobile application that serves as the companion app for Omi devices. This app enables users to interact with their Omi device, manage apps, and customize their experience.

## 📚 **[View Full App setup instructions in the documentation](https://docs.omi.me/doc/developer/AppSetup)**

### Quick Setup

Before getting started, make sure your device is connected and unlocked. If you're using an iPhone, ensure that Developer Mode is enabled — you can toggle this in the iPhone settings. For Android devices, make sure the device is connected and USB debugging is enabled in Developer Options

1. Navigate to the app directory:
   ```bash
   cd app
   ```

2. Run the setup script for your platform:
   ```bash
   # macOS/Linux: iOS
   bash setup.sh ios

   # macOS/Linux: Android
   bash setup.sh android
   ```

   ```powershell
   # Windows PowerShell: Android
   .\setup\scripts\setup.ps1 android
   ```

   `bash setup.sh ios` is the safe local-development path: it uses the local
   API/emulator harness and the `demo-omi-local` Firebase project. For a real
   iPhone, set `OMI_DEV_HOST` to the Mac's LAN address when the local harness is
   reachable from the device.

   iOS setup requires macOS/Xcode, so Windows developers should use the Android setup path.

### Mobile beta / dogfood

The mobile beta is an explicit production-data profile. It uses the production
Firebase project and user IDs, but routes serving traffic to
`https://api.omiapi.com/`, matching the macOS beta serving plane:

```bash
export FIREBASE_SERVICE_ACCOUNT_KEY=/secure/path/to/firebase-service-account.json
bash setup.sh ios beta

# Android beta uses the existing prod flavor and package
bash setup.sh android beta
```

The Firebase service account must be able to generate the production mobile
configuration, and the beta bundle ID must be registered with both Firebase and
the Apple team. Override the default bundle ID with
`OMI_MOBILE_BETA_BUNDLE_ID` when your team uses a different registered ID. The
beta build uses the `mobile_beta` profile and the `omi-beta://auth/callback`
scheme. Product traffic uses the beta serving API, while Google and Apple OAuth
remain on `https://api.omi.me/`; the beta must not be treated as a local-emulator
build.
 
3. Ensure GitHub SSH access is set up correctly for pulling certificates from repositories. After running the command below, if you're prompted for a passphrase, enter your SSH passphrase — or simply press Enter/Return if you haven't set one.
    ```bash
   cd ~/.ssh; ssh-add
   ```

4. To run the app, navigate to the app directory and use the following command:
   ```bash
   flutter run --flavor dev
   ```


### Building and Deploying to iPhone

To build and deploy the app to an iPhone so it can run independently from your laptop:

1. Build the iOS app with release mode and specific flavor:
   ```bash
   flutter build ios --flavor dev --release
   ```
   This produces an .app bundle at:
   ```
   build/ios/iphoneos/Runner.app
   ```

2. **Install directly from the .app bundle (recommended for local device install):**
   ```bash
   ios-deploy --bundle build/ios/iphoneos/Runner.app --debug
   ```
   This will install the app directly to your connected iPhone.

Once installed, the app will run on your iPhone independently from your development machine.

## Need Help?

- 💬 Join our [Discord Community](http://discord.omi.me)
