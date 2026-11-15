#!/usr/bin/env bash
# Render the actual pre-change cancellation source with the same synthetic fixture.
set -euo pipefail
cd "$(dirname "$0")/../.."
fixture_dir="$(mktemp -d test/widgets/yearly_baseline.XXXXXX)"
trap 'rm -rf "$fixture_dir"' EXIT
git show ac02feb05f0d6389f473e08a25980397b1348b0f:app/lib/pages/settings/widgets/cancel_subscription_sheet.dart > "$fixture_dir/before.dart"
cat > "$fixture_dir/baseline_test.dart" <<'DART'
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/gen/payments_wire.g.dart' as wire;
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import '../../support/recording_analytics.dart';
import '../yearly_retention_test.dart' as fixture;
import 'before.dart' as before;
void main() {
  setUp(() async {
    OmiColors.active = OmiPalette.light;
    SharedPreferences.setMockInitialValues({'uid':'synthetic-uid'});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
    final analytics = RecordingAnalytics();
    AnalyticsManager.configure(analytics.adapter);
    await AnalyticsManager.init();
  });
  tearDown(AnalyticsManager.resetForTesting);
  fixture.iosTestWidgets('historical cancellation baseline', (tester) async {
    await tester.runAsync(fixture.fonts);
    await fixture.pump(tester, before.CancelSubscriptionFlow(loadOffer: () async =>
      wire.GeneratedRetentionOfferResponse(eligible:true, percentOff:50, durationMonths:3,
        regularAmount:2999, discountedAmount:1500, currency:'usd')));
    await fixture.confirmStep(tester);
    await fixture.screenshot(tester, '001-mobile-ios-cancel-before');
  });
}
DART
flutter test --no-pub --dart-define=YEARLY_RETENTION_RENDER_OUTPUT=../.agent-artifacts/ui-evidence/yearly-retention "$fixture_dir/baseline_test.dart"
