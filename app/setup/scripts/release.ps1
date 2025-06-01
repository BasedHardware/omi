fvm flutter clean; fvm dart run build_runner build; Write-Host "1"
fvm flutter pub get
fvm flutter build appbundle --release --flavor prod -t lib/main_prod.dart
fvm flutter build apk --release --flavor prod -t lib/main_prod.dart 