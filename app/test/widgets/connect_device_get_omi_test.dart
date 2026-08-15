import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:shared_preferences/shared_preferences.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  tearDown(AnalyticsManager.resetForTesting);

  test('Get Omi action emits purchase intent and opens the store', () async {
    final analytics = _TestAnalyticsAdapter();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
    Uri? launchedUrl;

    await openOmiStore(
      launcher: (url) async {
        launchedUrl = url;
        return true;
      },
    );
    await AnalyticsManager.flushPending(force: true);

    expect(analytics.events, ['Get Omi Device Clicked']);
    expect(launchedUrl, Uri.parse('https://www.omi.me/?_ref=omi_connect_device'));
  });
}

class _TestAnalyticsAdapter implements AnalyticsAdapter {
  final List<String> events = [];

  @override
  bool get isInitialized => true;

  @override
  Future<void> init() async {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) => events.add(eventName);

  @override
  void alias({required String newUserId}) {}

  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}

  @override
  void setInteractionContext({String? screenName, required String target}) {}

  @override
  void enable() {}

  @override
  void disable() {}

  @override
  void reset() {}
}
