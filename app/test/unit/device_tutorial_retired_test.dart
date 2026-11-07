import 'dart:io';

import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/settings/device_settings.dart';
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
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/services.dart';
import 'package:omi/ui/prompts/prompt_queue.dart';

import '../../integration_test/journeys/support/hermetic_boot.dart';
import '../support/typed_conversation_screen.dart' show inertPendingWorkStore;

class _ConnectedCv1Provider extends ChangeNotifier implements DeviceProvider {
  _ConnectedCv1Provider(this.device);

  final BtDevice device;

  @override
  bool get isConnected => true;

  @override
  bool get isSyncStalled => false;

  @override
  BtDevice? get connectedDevice => device;

  @override
  BtDevice? get pairedDevice => device;

  @override
  int get batteryLevel => 85;

  @override
  bool get isCharging => false;

  @override
  bool get havingNewFirmware => false;

  @override
  String get latestStableFirmwareVersion => '';

  @override
  Future<void> getDeviceInfo() async {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  setUp(() async {
    final previousStore = PendingWorkStore.instance;
    final store = inertPendingWorkStore();
    PendingWorkStore.instance = store;
    addTearDown(() {
      PendingWorkStore.instance = previousStore;
      store.dispose();
    });
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({'deviceOnboardingCompleted': false});
    await SharedPreferencesUtil.init();
  });

  testWidgets('DeviceSettings does not render the device tutorial row for a connected Omi CV1 (#19236)', (
    tester,
  ) async {
    final cv1 = BtDevice(
      id: 'cv1-id',
      name: 'Omi',
      type: DeviceType.omi,
      rssi: -45,
      modelNumber: 'Omi CV 1',
      firmwareRevision: '2.1.0',
    );
    final provider = _ConnectedCv1Provider(cv1);
    addTearDown(provider.dispose);

    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(disableAnimations: true),
          child: child!,
        ),
        home: ChangeNotifierProvider<DeviceProvider>.value(
          value: provider,
          child: const DeviceSettings(),
        ),
      ),
    );
    await tester.pump();

    expect(find.text('How to Use Your Omi'), findsNothing);
    expect(find.text('Offline Sync'), findsOneWidget);
  });

  testWidgets('connecting an Omi CV1 on Home with deviceOnboardingCompleted false does not enqueue device-tutorial (#19236)', (
    tester,
  ) async {
    _stubHomePlugins();
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
    await tester.runAsync(() async {
      await JourneyHermeticBoot.start(
        extraPrefs: {
          'onboardingCompleted': true,
          'permissionsCompleted': true,
          'aiConsentGiven': true,
          'deviceOnboardingCompleted': false,
        },
      );
      try {
        await ServiceManager.init();
      } catch (_) {}
    });
    addTearDown(JourneyHermeticBoot.stop);

    PromptQueue.instance.reset();
    addTearDown(PromptQueue.instance.reset);

    await JourneyHermeticBoot.pumpPage(tester, page: const HomePage(), providers: _homeProviders());

    final cv1 = BtDevice(
      id: 'cv1-id',
      name: 'Omi',
      type: DeviceType.omi,
      rssi: -45,
      modelNumber: 'Omi CV 1',
      firmwareRevision: '2.1.0',
    );
    final deviceProvider = tester.element(find.byType(HomePage)).read<DeviceProvider>();
    deviceProvider.pairedDevice = cv1;
    deviceProvider.connectedDevice = cv1;
    deviceProvider.isConnected = true;

    // Hold prompts in pendingIds while the 2s announcement timer fires and onDeviceConnected is invoked.
    deviceProvider.setFirmwareUpdateInProgress(true);
    await tester.pump(const Duration(seconds: 2));
    deviceProvider.onDeviceConnected?.call(cv1);
    await tester.pump();

    expect(PromptQueue.instance.pendingIds, isNot(contains('device-tutorial')));
    expect(PromptQueue.instance.showingId, isNot('device-tutorial'));
    expect(PromptQueue.instance.pendingIds, contains('firmware-announcements'));

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 900));
  });

  test('Home and DeviceSettings do not wire InteractiveDeviceOnboardingWrapper (#19236)', () {
    final homeSource = File('lib/pages/home/page.dart').readAsStringSync();
    final deviceSettingsSource = File('lib/pages/settings/device_settings.dart').readAsStringSync();

    expect(homeSource, isNot(contains('InteractiveDeviceOnboardingWrapper')));
    expect(homeSource, isNot(contains('_checkDeviceOnboarding')));
    expect(deviceSettingsSource, isNot(contains('InteractiveDeviceOnboardingWrapper')));
    expect(deviceSettingsSource, isNot(contains('l10n.deviceTutorial')));
  });
}

List<SingleChildWidget> _homeProviders() {
  return [
    ChangeNotifierProvider(create: (_) => AuthenticationProvider(initializeListeners: false)),
    ChangeNotifierProvider(create: (_) => CaptureProvider(localSegmentStore: LocalSegmentStore.disabled())),
    ChangeNotifierProvider(create: (_) => LocalRecordingsProvider(initialize: false)),
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
    ChangeNotifierProvider(
      create: (_) => SpeakerTagPromptsProvider(
        fetchPrompts: () async => const ApiSuccess(GeneratedSpeakerTagPromptsResponse()),
      ),
    ),
  ];
}

void _stubHomePlugins() {
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  const channels = [
    'flutter_foreground_task/methods',
    'flutter.baseflow.com/geolocator',
    'flutter.baseflow.com/permissions/methods',
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
          return '/tmp/omi-device-tutorial-retired';
        default:
          return null;
      }
    });
  }
  messenger.setMockStreamHandler(
    const EventChannel('com.omi/phone_calls/events'),
    MockStreamHandler.inline(onListen: (args, sink) {}, onCancel: (args) {}),
  );
}
