import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/announcement_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/locale_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/account_cutover/account_cutover_runtime.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/services.dart';

import '../../integration_test/journeys/support/hermetic_boot.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('HomePageWrapper does not enable notifications after dispose during permission await', (tester) async {
    _stubPlugins(permissionStatusDelay: const Duration(milliseconds: 50));
    setupFirebaseCoreMocks();
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp(
        options: const FirebaseOptions(
          apiKey: 'fake',
          appId: '1:1:ios:fake',
          messagingSenderId: '1',
          projectId: 'demo-omi-local',
        ),
      );
    }
    AccountCutoverRuntime.instance.resetForTesting();
    await tester.runAsync(() async {
      await JourneyHermeticBoot.start(
        extraPrefs: {'onboardingCompleted': true, 'permissionsCompleted': true, 'aiConsentGiven': true},
      );
      try {
        await ServiceManager.init();
      } catch (_) {}
    });
    addTearDown(JourneyHermeticBoot.stop);
    addTearDown(AccountCutoverRuntime.instance.resetForTesting);

    expect(SharedPreferencesUtil().notificationsEnabled, isFalse);

    await JourneyHermeticBoot.pumpPage(tester, page: const HomePageWrapper(), providers: _homeProviders());
    expect(find.byType(HomePage), findsOneWidget);

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    // Complete the held Permission.notification.isGranted Future after unmount.
    await tester.pump(const Duration(milliseconds: 50));

    expect(find.byType(HomePage), findsNothing);
    expect(SharedPreferencesUtil().notificationsEnabled, isFalse);

    // Flush HomePage work that origin/main still leaves pending (2s announcement
    // Future.delayed and <1s prewarm Timers). This is not the assertion.
    await tester.pump(const Duration(milliseconds: 2100));
    expect(tester.takeException(), isNull);
  });
}

List<SingleChildWidget> _homeProviders() {
  return [
    ChangeNotifierProvider(create: (_) => AuthenticationProvider(initializeListeners: false)),
    ChangeNotifierProvider(create: (_) => CaptureProvider(localSegmentStore: LocalSegmentStore.disabled())),
    ChangeNotifierProvider(create: (_) => LocalRecordingsProvider()),
    ChangeNotifierProvider(
      create: (_) => DeviceProvider(
        bleDiagnosticsLoader: (_) async => throw StateError('fixture: BLE diagnostics unused'),
        findDeviceRunner: (_) async => false,
      ),
    ),
    ChangeNotifierProvider(create: (_) => AnnouncementProvider()),
    ChangeNotifierProvider(create: (_) => ActionItemsProvider()),
    ChangeNotifierProvider(create: (_) => SyncProvider(startBackgroundSync: false)),
    ChangeNotifierProvider(create: (_) => TaskIntegrationProvider()),
    ChangeNotifierProvider(create: (_) => PhoneCallProvider.forTesting()),
    ChangeNotifierProvider(create: (_) => GoalsProvider()),
    ChangeNotifierProxyProvider<AppProvider, AddAppProvider>(
      create: (_) => AddAppProvider(),
      update: (_, app, previous) => (previous?..setAppProvider(app)) ?? (AddAppProvider()..setAppProvider(app)),
    ),
    ChangeNotifierProvider(
      create: (_) =>
          UserProvider(privateCloudSyncFetcher: () async => false, privateCloudSyncSetter: (_) async => true),
    ),
    ChangeNotifierProvider(create: (_) => MemoriesProvider()),
    ChangeNotifierProvider(create: (_) => PeopleProvider()),
    ChangeNotifierProvider(create: (_) => LocaleProvider()),
  ];
}

void _stubPlugins({required Duration permissionStatusDelay}) {
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  const channels = [
    'flutter_foreground_task/methods',
    'flutter.baseflow.com/geolocator',
    'dev.fluttercommunity.plus/connectivity',
    'dev.fluttercommunity.plus/connectivity_status',
    'xyz.luan/audioplayers',
    'plugins.flutter.io/path_provider',
    'plugins.flutter.io/shared_preferences',
    'plugins.flutter.io/firebase_messaging',
    'com.omi/phone_calls',
    'com.omi/phone_calls/events',
  ];
  for (final name in channels) {
    messenger.setMockMethodCallHandler(MethodChannel(name), (call) async {
      switch (call.method) {
        case 'check':
          return ['wifi'];
        case 'checkPermission':
        case 'checkServiceStatus':
          return 1;
        case 'getAll':
          return <String, Object>{};
        case 'getApplicationDocumentsDirectory':
        case 'getTemporaryDirectory':
        case 'getApplicationSupportDirectory':
          return '/tmp/omi-home-mounted-guard';
        default:
          return null;
      }
    });
  }
  messenger.setMockMethodCallHandler(const MethodChannel('flutter.baseflow.com/permissions/methods'), (call) async {
    if (call.method == 'checkPermissionStatus' || call.method == 'checkPermission') {
      await Future<void>.delayed(permissionStatusDelay);
      return 1;
    }
    if (call.method == 'checkServiceStatus') return 1;
    return null;
  });
  messenger.setMockStreamHandler(
    const EventChannel('com.omi/phone_calls/events'),
    MockStreamHandler.inline(onListen: (args, sink) {}, onCancel: (args) {}),
  );
}
