#!/bin/bash

# Print commands and exit on error
set -e

echo "🧹 Cleaning everything..."

# Function to safely remove files/directories
safe_remove() {
    if [ -e "$1" ]; then
        rm -rf "$1"
        echo "Removed $1"
    fi
}

# Clean Flutter
flutter clean
safe_remove "pubspec.lock"
safe_remove ".dart_tool/"
safe_remove "build/"
safe_remove ".flutter-plugins"
safe_remove ".flutter-plugins-dependencies"

# Clean iOS specific
if [ -d "ios" ]; then
    echo "Cleaning iOS files..."
    cd ios
    safe_remove "Pods/"
    safe_remove "Podfile.lock"
    safe_remove ".symlinks/"
    safe_remove "Flutter/Flutter.framework"
    safe_remove "Flutter/Flutter.podspec"
    safe_remove "Flutter/.last_build_id"
    safe_remove "Flutter/Generated.xcconfig"
    safe_remove "Flutter/Debug.xcconfig"
    safe_remove "Flutter/Release.xcconfig"
    cd ..
fi

# Clean Android specific
if [ -d "android" ]; then
    echo "Cleaning Android files..."
    cd android
    if [ -f "gradlew" ]; then
        chmod +x gradlew
        ./gradlew clean
    else
        echo "Warning: gradlew not found in android directory"
    fi
    safe_remove ".gradle"
    safe_remove "build/"
    safe_remove "app/build/"
    cd ..
fi

echo "📦 Getting packages..."
flutter clean
flutter pub get

echo "🏗️ Running build_runner..."
# Force build_runner to create new files
dart run build_runner clean
dart run build_runner build --delete-conflicting-outputs

# Setup iOS if directory exists
if [ -d "ios" ]; then
    echo "🍎 Setting up iOS..."
    cd ios
    pod deintegrate || true
    pod cache clean --all
    pod repo update
    pod install --repo-update
    cd ..

    echo "🍎 Building iOS for dev..."
    flutter build ios --no-codesign --flavor dev
fi

# # Setup Android if directory exists
# if [ -d "android" ]; then
#     echo "🤖 Setting up Android..."
#     cd android
#     if [ -f "gradlew" ]; then
#         chmod +x gradlew
#         ./gradlew build
#     else
#         echo "Warning: gradlew not found in android directory"
#     fi
#     cd ..
# fi

echo "✅ Build completed! Try running the app now."

# Optionally, you can uncomment these lines to automatically build for release
echo "🚀 Building release versions..."
# flutter build appbundle --release --flavor prod -t lib/main_prod.dart
# flutter build apk --release --flavor prod -t lib/main_prod.dart
# flutter build ios --release --flavor prod -t lib/main_prod.dart

