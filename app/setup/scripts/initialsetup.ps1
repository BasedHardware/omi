# Upgrade Flutter
Write-Host "Upgrading Flutter..."
flutter upgrade

# Get Flutter dependencies
Write-Host "Getting Flutter dependencies..."
Set-Location -Path "app/AppWithWearable"
flutter pub get

# Install iOS pods
Write-Host "Installing iOS pods..."
gem install cocoapods
Set-Location -Path "ios"
pod install
pod repo update
Set-Location -Path ".."

# TODO Install Android dependencies?
# ...

# Create public client env files from template
Write-Host "Creating public client env files..."
Copy-Item -Path ".client.env.example" -Destination ".client.dev.env"
Copy-Item -Path ".client.env.example" -Destination ".client.env"

# Prompt user to review public client config
Write-Host "Review app/.client.dev.env and app/.client.env. Do not add private API keys or server-only secrets."
Write-Host "Press Enter to continue after reviewing the public client config..."
$null = Read-Host

# Run Build Runner
Write-Host "Running Build Runner..."
dart run build_runner build

Write-Host "Setup complete. You can now run the app."
