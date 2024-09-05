## Friend App

Check out https://docs.basedhardware.com/get_started/Setup/ for a guide on how to set up the app.

dart run build_runner build --delete-conflicting-outputs 
flutter run --flavor dev -t lib/main.dart
flutter run --flavor dev -t lib/main.dart --release
flutter build apk -t lib/main.dart --release --flavor dev
flutter build appbundle -t lib/main.dart --release --flavor prod
export PATH="$PATH:/Volumes/Piyush/SDK/flutter/bin"