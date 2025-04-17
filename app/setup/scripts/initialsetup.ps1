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

# Create .env file from template
Write-Host "Creating .env file..."
Copy-Item -Path ".env.template" -Destination ".dev.env"
Copy-Item -Path ".env.template" -Destination ".prod.env"

# Prompt user to add API keys to .env file
Write-Host "Please add your API keys to the .env file."
Write-Host "Press Enter to continue after adding the keys..."
$null = Read-Host

# Run Build Runner
Write-Host "Running Build Runner..."
dart run build_runner build

Write-Host "Setup complete. You can now run the app." 