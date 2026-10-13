import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../spine/c7_registry_test.dart' show RecordingAdapter;

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
        appName: 'Omi Test', packageName: 'com.omi.test', version: '1.0.0', buildNumber: '1', buildSignature: '');
    await SharedPreferencesUtil.init();
  });
  tearDown(AnalyticsManager.resetForTesting);
  test('contextual sources survive typed funnel emission without collapsing to unknown', () async {
    final adapter = RecordingAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    final analytics = AnalyticsManager();
    const sources = [
      'budget_80_percent',
      'budget_100_percent',
      'proactive_agent_gate',
      'screen_context_gate',
      'mcp_daily_cap'
    ];
    for (final source in sources) {
      analytics.paywallOpened(source, currentPlan: 'plus');
      analytics.upgradePlanSelected(plan: 'operator', billingInterval: 'year', source: source);
    }
    analytics.upgradeSucceeded(previousPlan: 'plus', newPlan: 'operator', billingInterval: 'year');
    analytics.upgradeCancelled();
    await AnalyticsManager.flushPending(force: true);
    await AnalyticsManager.flushPending(force: true);
    final opened = adapter.events.where((event) => event.$1 == 'Paywall Opened').toList();
    final selected = adapter.events.where((event) => event.$1 == 'Upgrade Plan Selected').toList();
    expect(opened.map((event) => event.$2['source']), sources);
    expect(selected.map((event) => event.$2['source']), sources);
    expect(selected.every((event) => event.$2['plan'] == 'operator' && event.$2['billing_interval'] == 'year'), isTrue);
    final attributed = adapter.events.singleWhere((event) => event.$1 == 'Upgrade Succeeded Attributed');
    expect(attributed.$2['plan'], 'operator');
    expect(attributed.$2['billing_interval'], 'year');
    expect(adapter.events.where((event) => event.$1 == 'Upgrade Succeeded'), hasLength(1));
    expect(adapter.events.where((event) => event.$1 == 'Upgrade Cancelled'), hasLength(1));
  });
}
