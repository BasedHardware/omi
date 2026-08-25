flutter clean; dart run build_runner build; Write-Host "1"
flutter pub get
flutter build appbundle --release --flavor prod
flutter build apk --release --flavor prod