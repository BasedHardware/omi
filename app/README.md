# Omi App

The Omi App is a Flutter-based mobile application that serves as the companion app for Omi devices. This app enables users to interact with their Omi device, manage apps, and customize their experience.

## 📚 **[View Full App setup instructions in the documentation](https://docs.omi.me/docs/developer/AppSetup)**

### Quick Setup
Before getting started make sure your device is unlocked and Iphone is in Devmode this can be toggles in Iphone settings

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
 
3. Ensure GitHub access is available for pulling private repositories.
 cd ~/.ssh; ssh-add  

4. Run the app:
   ```bash
   flutter run --flavor dev

   ```
5. If no Github Access.
`` bash 

flutter run --flavor dev -d "iPhone 16 Plus"

command will allow you to run it on a MACos Simulator 
```
6. open xcode with 
```bash
open ios/Runner.xcworkspace
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
