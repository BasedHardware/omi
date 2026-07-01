#!/bin/bash

# Upgrade Flutter
echo "Upgrading Flutter..."
flutter upgrade

# Get Flutter dependencies
echo "Getting Flutter dependencies..."
cd apps/AppWithWearable
flutter pub get

# Install iOS pods
echo "Installing iOS pods..."
sudo gem install cocoapods
cd ios
pod install
pod repo update
cd ..

# TODO Install Android dependencies?
# ...

# Create public client env files from template
echo "Creating public client env files..."
cat .client.env.example > .client.dev.env
cat .client.env.example > .client.env

# Prompt user to review public client config
echo "Review app/.client.dev.env and app/.client.env. Do not add private API keys or server-only secrets."
read -p "Press enter to continue after reviewing the public client config."
../scripts/check-public-client-secrets.py --env-file .client.dev.env --env-file .client.env || exit 1

# Run Build Runner
echo "Running Build Runner..."
dart run build_runner build

echo "Setup complete. You can now run the app."
