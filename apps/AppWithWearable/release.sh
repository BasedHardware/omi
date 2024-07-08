flutter clean; dart run build_runner build; echo "1"
flutter pub get
flutter build appbundle --release --flavor prod -t lib/main_prod.dart
flutter build apk --release --flavor prod -t lib/main_prod.dart