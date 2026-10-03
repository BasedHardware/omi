import 'package:calendar_date_picker2/calendar_date_picker2.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_core_platform_interface/test.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/conversations/day_conversations_page.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/announcement_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
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
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/services.dart';

import '../../integration_test/journeys/support/hermetic_boot.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('Home shows the calendar button; one picked day opens the day page', (tester) async {
    await _pumpHomePage(tester);
    final button = find.byKey(const ValueKey('home_calendar_button'));
    expect(button, findsOneWidget);

    final provider = Provider.of<ConversationProvider>(tester.element(find.byType(HomePage)), listen: false);
    provider.selectedStartDate = DateTime(2026, 6, 1);
    provider.selectedEndDate = DateTime(2026, 6, 3);

    await tester.tap(button);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));
    expect(find.text('Filter by date'), findsOneWidget);

    tester.widget<CalendarDatePicker2>(find.byType(CalendarDatePicker2)).onValueChanged?.call([DateTime(2026, 7, 10)]);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.byKey(const Key('date_range_done')));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(find.byType(DayConversationsPage), findsOneWidget);

    expect(provider.selectedStartDate, DateTime(2026, 6, 1), reason: 'a day route never mutates the feed filter');
    expect(provider.selectedEndDate, DateTime(2026, 6, 3));
    await _disposeHomePage(tester);
  });

  testWidgets('a picked range filters the feed and the chip clears it', (tester) async {
    await _pumpHomePage(tester);
    await tester.tap(find.byKey(const ValueKey('home_calendar_button')));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 400));

    tester
        .widget<CalendarDatePicker2>(find.byType(CalendarDatePicker2))
        .onValueChanged
        ?.call([DateTime(2026, 7, 1), DateTime(2026, 7, 3)]);
    await tester.pump(const Duration(milliseconds: 100));
    await tester.tap(find.byKey(const Key('date_range_done')));
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    final context = tester.element(find.byType(HomePage));
    final provider = Provider.of<ConversationProvider>(context, listen: false);
    expect(provider.selectedStartDate, isNotNull);
    expect(provider.selectedEndDate, isNotNull);
    expect(provider.selectedStartDate != provider.selectedEndDate, isTrue,
        reason: 'a two-day pick must become a range filter');

    final chip = find.byKey(const ValueKey('home_date_filter'));
    expect(chip, findsOneWidget);
    await tester.tap(chip);
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));
    expect(provider.selectedStartDate, isNull);
    expect(find.byKey(const ValueKey('home_date_filter')), findsNothing);
    await _disposeHomePage(tester);
  });
}

Future<void> _disposeHomePage(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 900));
}

Future<void> _pumpHomePage(WidgetTester tester) async {
  _stubPlugins();
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
      extraPrefs: {'onboardingCompleted': true, 'permissionsCompleted': true, 'aiConsentGiven': true},
    );
    try {
      await ServiceManager.init();
    } catch (_) {}
  });
  addTearDown(JourneyHermeticBoot.stop);

  await JourneyHermeticBoot.pumpPage(tester, page: const HomePage(), providers: _homeProviders());
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
    ChangeNotifierProvider(
      create: (_) => SpeakerTagPromptsProvider(
        fetchPrompts: () async => const ApiSuccess(GeneratedSpeakerTagPromptsResponse()),
      ),
    ),
  ];
}

void _stubPlugins() {
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
          return '/tmp/omi-home-calendar';
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
