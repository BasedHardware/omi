# Omi App

The Omi App is a Flutter-based mobile application that serves as the companion app for Omi devices. This app enables users to interact with their Omi device, manage apps, and customize their experience.

## 📚 **[View Full App setup instructions in the documentation](https://docs.omi.me/doc/developer/AppSetup)**

### Quick Setup

Before getting started, make sure your device is connected and unlocked. If you're using an iPhone, ensure that Developer Mode is enabled — you can toggle this in the iPhone settings. For Android devices, make sure the device is connected and USB debugging is enabled in Developer Options

1. Navigate to the app directory:
   ```bash
   cd app
   ```

2. Run setup script:
   ```bash
   # For iOS
   bash setup.sh ios

   # For Android
   bash setup.sh android
   ```
 
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

# AGENTS.md — Additions Required by Issue #4905
#
# Add the following section to the existing app/AGENTS.md file.
# Insert it BEFORE the final section or at the top-level after the existing agent rules.
# ──────────────────────────────────────────────────────────────────────────────

## Flow Doc Governance (Mandatory)

> **Any PR with significant app changes MUST update the corresponding flow doc.**

The three canonical flow docs live in `app/docs/flows/`:

| Doc | File | Update when... |
|---|---|---|
| UI Flow | `docs/flows/ui-flow.md` | Navigation, screens, or routing changes in `lib/pages/**` or `lib/core/app_shell.dart` |
| Data Flow | `docs/flows/data-flow.md` | API modules, schema, WebSocket events, or deep-link handlers change |
| State Management | `docs/flows/state-management.md` | Provider registrations, ProxyProvider chains, or `lib/providers/**` change |

Generated YAML machine-diffable artifacts live in `docs/flows/generated/` — regenerate after
any relevant change using the scripts in `scripts/agent/`.

For full operational guidance (build bootstrap, codegen rules, native bridge, permissions,
test strategy, l10n, security), see `app/CLAUDE.md`.


- 💬 Join our [Discord Community](http://discord.omi.me)
