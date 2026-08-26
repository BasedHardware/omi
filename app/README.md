# Omi App

The Omi App is a Flutter-based mobile application that serves as the companion app for Omi devices. This app enables users to interact with their Omi device, manage apps, and customize their experience.

## 📚 **[View Full App setup instructions in the documentation](https://docs.omi.me/doc/developer/AppSetup)**

### Quick Setup

Before getting started, make sure your device is connected and unlocked. If you're using an iPhone, ensure that Developer Mode is enabled — you can toggle this in the iPhone settings. For Android devices, make sure the device is connected and USB debugging is enabled in Developer Options

1. Start the local backend harness from the **repo root**. `setup.sh` builds
   against it but does not start it, so do this first or the app will launch with
   nothing to talk to:
   ```bash
   make dev-init   # once: creates backend/.venv and copies the env template
   make dev-up     # Firestore + Auth emulators and the Python API on :8000

   # No provider API keys? Use fake providers:
   PROVIDER_MODE=offline make dev-up
   ```

   `make dev-init` builds `backend/.venv` from whatever `python3` resolves to,
   and the backend requires **Python 3.11** (not 3.12+). The harness also needs a
   Java runtime and `firebase-tools`/`npx`; `make dev-up` names what's missing.

   `make dev-status` shows what came up; `make dev-down` stops it. Ports, seeded
   users, and troubleshooting: [`docs/runbooks/local-emulator-manual-qa.md`](../docs/runbooks/local-emulator-manual-qa.md).

2. Navigate to the app directory:
   ```bash
   cd app
   ```

3. Run the setup script for your platform:
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
   iPhone, set `OMI_DEV_HOST` to the Mac's LAN or Tailscale address before
   running both `setup.sh ios` and `make dev-up` (export it so both commands
   see it) — the harness now binds there too, not just the app build.

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
 
4. Ensure GitHub SSH access is set up correctly for pulling certificates from repositories. After running the command below, if you're prompted for a passphrase, enter your SSH passphrase — or simply press Enter/Return if you haven't set one.
    ```bash
   cd ~/.ssh; ssh-add
   ```

5. To run the app, navigate to the app directory and use the following command:
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
