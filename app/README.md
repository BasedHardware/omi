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

### Overview

The app uses Firebase for authentication, storage, and other services. It supports multiple environments (development and production) with separate Firebase configurations.

### Setup Instructions

1. **Create Firebase Projects**:
   - Create separate Firebase projects for development and production environments at [Firebase Console](https://console.firebase.google.com/)
   - For each project, add both Android and iOS apps with the appropriate package names/bundle IDs

2. **Download Configuration Files**:
   - For Android: Download `google-services.json` for each environment
   - For iOS: Download `GoogleService-Info.plist` for each environment
   - Place these files in the appropriate directories as specified in the setup script

3. **Configure Firebase Options**:
   - The app includes Firebase configuration files in `app/lib/firebase_options_dev.dart` and `app/lib/firebase_options_prod.dart`
   - These files contain the default Firebase options for each environment

### Using Custom Firebase Parameters

The app supports customizing Firebase parameters without modifying the default configurations:

1. **Development Environment**:
   ```dart
   // Example of using custom development Firebase options
   await Firebase.initializeApp(
     options: dev.DefaultFirebaseOptions.customAndroid(
       projectId: 'your-custom-dev-project-id',
       // Add other custom parameters as needed
     ),
     name: 'dev',
   );
   ```

2. **Production Environment**:
   ```dart
   // Example of using custom production Firebase options
   await Firebase.initializeApp(
     options: prod.DefaultFirebaseOptions.customIOS(
       projectId: 'your-custom-prod-project-id',
       // Add other custom parameters as needed
     ),
     name: 'prod',
   );
   ```

3. **Available Parameters**:
   - `apiKey`: Firebase API key
   - `appId`: Firebase application ID
   - `messagingSenderId`: Firebase messaging sender ID
   - `projectId`: Firebase project ID
   - `storageBucket`: Firebase storage bucket
   - `androidClientId`: Android client ID (for iOS configuration)
   - `iosClientId`: iOS client ID
   - `iosBundleId`: iOS bundle ID

### Remote Config

To use Firebase Remote Config:

1. Set up Remote Config in the Firebase Console
2. Define parameters and their default values
3. Access these values in your app using the Firebase Remote Config API

## Need Help?

- 💬 Join our [Discord Community](http://discord.omi.me)
