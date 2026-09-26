import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../spine/c7_registry_test.dart' show RecordingAdapter, emissionPayloads;

/// Adapter payloads captured from leftover bool-only public methods at
/// `b4785879e9cc87624b8d501e2f9605ef9e6311e3`, after the main-forward merges
/// and before those methods called [TypedEvents.emit].
const c8LeftoverBoolPreMigrationSha = 'b4785879e9cc87624b8d501e2f9605ef9e6311e3';

void fireC8LeftoverBools(AnalyticsManager analytics) {
  analytics.showDiscardedMemoriesToggled(false);
  analytics.showDiscardedMemoriesToggled(true);
  analytics.showDiscardedConversationsToggled(false);
  analytics.showDiscardedConversationsToggled(true);
  analytics.deletedConversationsFilterToggled(false);
  analytics.deletedConversationsFilterToggled(true);
  analytics.appsFilterMyApps(enabled: false);
  analytics.appsFilterMyApps(enabled: true);
  analytics.appsFilterInstalled(enabled: false);
  analytics.appsFilterInstalled(enabled: true);
  analytics.dailySummaryToggled(enabled: false);
  analytics.dailySummaryToggled(enabled: true);
  analytics.aiAppGeneratorAppGenerated(success: false);
  analytics.aiAppGeneratorAppGenerated(success: true);
  analytics.actionItemsViewToggled(false);
  analytics.actionItemsViewToggled(true);
  analytics.phoneCallStarted();
  analytics.phoneCallStarted(contactName: 'synthetic');
}

List<List<Object>> c8LeftoverBoolGoldens(Map<String, Object> globals) => [
      [
        'Show Discarded Memories Toggled',
        {...globals, 'show_discarded': false}
      ],
      [
        'Show Discarded Memories Toggled',
        {...globals, 'show_discarded': true}
      ],
      [
        'Show Discarded Conversations Toggled',
        {...globals, 'show_discarded': false}
      ],
      [
        'Show Discarded Conversations Toggled',
        {...globals, 'show_discarded': true}
      ],
      [
        'Deleted Conversations Filter Toggled',
        {...globals, 'show_deleted': false}
      ],
      [
        'Deleted Conversations Filter Toggled',
        {...globals, 'show_deleted': true}
      ],
      [
        'Apps Filter My Apps',
        {...globals, 'enabled': false}
      ],
      [
        'Apps Filter My Apps',
        {...globals, 'enabled': true}
      ],
      [
        'Apps Filter Installed',
        {...globals, 'enabled': false}
      ],
      [
        'Apps Filter Installed',
        {...globals, 'enabled': true}
      ],
      [
        'Daily Summary Toggled',
        {...globals, 'enabled': false}
      ],
      [
        'Daily Summary Toggled',
        {...globals, 'enabled': true}
      ],
      [
        'AI App Generator App Generated',
        {...globals, 'success': false}
      ],
      [
        'AI App Generator App Generated',
        {...globals, 'success': true}
      ],
      [
        'Action Items View Toggled',
        {...globals, 'grouped_view': false}
      ],
      [
        'Action Items View Toggled',
        {...globals, 'grouped_view': true}
      ],
      [
        'Phone Call Started',
        {...globals, 'has_contact_name': false}
      ],
      [
        'Phone Call Started',
        {...globals, 'has_contact_name': true}
      ],
    ];

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    PackageInfo.setMockInitialValues(
        appName: 'Omi Test', packageName: 'com.omi.test', version: '1.0.543', buildNumber: '992', buildSignature: '');
    await SharedPreferencesUtil.init();
  });
  tearDown(AnalyticsManager.resetForTesting);

  test('C8 leftover-bool public methods match goldens pinned at $c8LeftoverBoolPreMigrationSha', () async {
    final adapter = RecordingAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    fireC8LeftoverBools(AnalyticsManager());
    await AnalyticsManager.flushPending(force: true);
    await AnalyticsManager.flushPending(force: true);
    final globals = <String, Object>{
      'app_platform': PlatformService.isIOS ? 'ios' : (PlatformService.isAndroid ? 'android' : 'unknown'),
      'app_version': '1.0.543',
      'app_build': '992',
    };
    expect(emissionPayloads(adapter.events), c8LeftoverBoolGoldens(globals));
    expect(adapter.events.every((event) => !event.$2.containsKey('correlation_id')), isTrue);
    expect(adapter.events.every((event) => !event.$2.containsKey('contact_name')), isTrue);
    expect(AnalyticsManager.queuedEventCountForTesting, 0);
  });
}
