#!/usr/bin/env bash
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

# Keep this legacy release helper on the same profile/auth contract as the
# setup wrapper. Only setup-owned keys are updated; developer-owned .env values
# remain intact.
source setup.sh >/dev/null
setup_app_env mobile_beta "$BETA_API_BASE_URL"
scripts/validate_mobile_build_config.sh --flavor prod --profile mobile_beta

flutter clean
flutter pub get
dart run build_runner build --delete-conflicting-outputs
flutter build appbundle --release --flavor prod -t lib/main_prod.dart \
  --dart-define=OMI_APP_PROFILE=mobile_beta
flutter build apk --release --flavor prod -t lib/main_prod.dart \
  --dart-define=OMI_APP_PROFILE=mobile_beta
