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

# Create .env file from template
echo "Creating .env file..."
cat .env.template > .dev.env
cat .env.template > .prod.env

# Prompt user to add API keys to .env file
echo "Please add your API keys to the .env file."
read -p "Press enter to continue after adding the keys."

# Run Build Runner
echo "Running Build Runner..."
dart run build_runner build

echo "Setup complete. You can now run the app."
