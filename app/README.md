# Omi App

The Omi App is a Flutter-based mobile application that serves as the companion app for Omi devices. This app enables users to interact with their Omi device, manage apps, and customize their experience.

## 📚 **[View Full App setup instructions in the documentation](https://docs.omi.me/docs/developer/AppSetup)**

## What's in the Documentation?

### 🛠 Development Setup
- **Firebase Setup**: Complete guide for configuring Firebase authentication and services
- **Environment Setup**: Step-by-step guide for .env configuration and API keys
- **Build Configuration**: Instructions for build runner and platform-specific setups
- **Manual Setup Option**: Alternative to automated setup for custom configurations
- **Troubleshooting Guide**: Common setup issues and their solutions

### 🚀 Advanced Topics
- **Backend Integration**: Guide for connecting to custom backend services
- **Production Setup**: Detailed Firebase configuration for production environment
- **Authentication**: Complete OAuth setup including SHA key generation
- **Multi-Environment**: Managing development and production configurations
- **Platform Specifics**: iOS and Android platform-specific requirements

### Quick Setup

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

3. Run the app:
   ```bash
   flutter run --flavor dev
   ```

## Firebase Configuration

The app supports two methods for Firebase configuration:

### 1. Environment Variables (Recommended)

Firebase credentials can be loaded from environment variables, which is the recommended approach for security and flexibility:

1. Update the `.dev.env` file with your Firebase project details:
   ```
   # Firebase Configuration
   FIREBASE_ANDROID_API_KEY=your_android_api_key
   FIREBASE_ANDROID_APP_ID=your_android_app_id
   FIREBASE_IOS_API_KEY=your_ios_api_key
   FIREBASE_IOS_APP_ID=your_ios_app_id
   FIREBASE_MESSAGING_SENDER_ID=your_messaging_sender_id
   FIREBASE_PROJECT_ID=your_project_id
   FIREBASE_STORAGE_BUCKET=your_storage_bucket
   FIREBASE_ANDROID_CLIENT_ID=your_android_client_id
   FIREBASE_IOS_CLIENT_ID=your_ios_client_id
   FIREBASE_IOS_BUNDLE_ID=your_ios_bundle_id
   ```

2. Run the build_runner to generate the necessary files:
   ```bash
   dart run build_runner build
   ```

3. The app will automatically use these environment variables for Firebase initialization.

### 2. Hardcoded Configuration (Fallback)

The app maintains hardcoded Firebase configurations as a fallback mechanism. If environment variables are not set or are incomplete, the app will automatically fall back to using the hardcoded configuration files:

- `lib/firebase_options_dev.dart` for development
- `lib/firebase_options_prod.dart` for production

## Need Help?

- 💬 Join our [Discord Community](http://discord.omi.me)
