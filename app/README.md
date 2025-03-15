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

## Need Help?

- 💬 Join our [Discord Community](http://discord.omi.me)

## Troubleshooting

### iOS Setup Issues with Ruby Gems

If you encounter Ruby gem dependency errors during iOS setup (particularly with fastlane), follow these steps:

1. Install Bundler (if not already installed):
   ```bash
   sudo gem install bundler
   ```

2. Create a Gemfile in the app directory with required gems:
   ```bash
   cat > Gemfile << EOL
   source "https://rubygems.org"

   gem "fastlane"
   gem "cocoapods"
   gem "nkf"
   EOL
   ```

3. Install gems using Bundler:
   ```bash
   bundle install
   ```

4. Run the iOS setup using Bundler:
   ```bash
   bundle exec bash setup.sh ios
   ```

This approach ensures all required Ruby dependencies are properly installed and managed.
