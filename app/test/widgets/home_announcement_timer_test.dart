import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';
import 'package:package_info_plus/package_info_plus.dart';

import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/home/home_navigation.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/announcement_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/locale_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/experiments/pendant_absence.dart';
import 'package:omi/ui/prompts/prompt_queue.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart' show AnalyticsManager;

import '../../integration_test/journeys/support/hermetic_boot.dart';
import '../support/crashlytics_recorder.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('HomePage announcement delay is cancelled on dispose', (tester) async {
    await _pumpHomePage(tester);
    // pumpPage already ran one frame, which arms the 2s announcement Timer.

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    // Flush tab-prewarm timers (<1s) without elapsing the 2s announcement delay.
    // Advancing a full 2s would fire the old Future.delayed and hide the leak.
    await tester.pump(const Duration(milliseconds: 900));
    expect(tester.takeException(), isNull);
    expect(find.byType(HomePage), findsNothing);
    // Test end is the assertion: Flutter fails if the 2s announcement Timer is still pending.
  });

  testWidgets('HomePage tab prewarm timers are cancelled on dispose', (tester) async {
    await _pumpHomePage(tester);
    // initState arms one Timer per non-selected IndexedStack slot (350ms + n*180ms).

    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pump();
    // Flush Duration.zero work (Upgrader.initialize) without elapsing the 350ms
    // first prewarm delay. A leftover prewarm Timer still fails _verifyInvariants.
    await tester.pump(const Duration(milliseconds: 1));
    // A fifth HomePage Timer that is still pending here fails the same way without
    // being stored on State. Duration.zero work that fires in this 1ms pump would
    // not; CaptureLifetime would be required to assert list membership itself.
    expect(tester.takeException(), isNull);
    expect(find.byType(HomePage), findsNothing);
  });

  testWidgets('system back on another tab returns to the Home tab first (D6)', (tester) async {
    await _pumpHomePage(tester);
    final home = tester.element(find.byType(HomePage)).read<HomeProvider>();
    home.setIndex(HomeProvider.tasksTab);
    await tester.pump();

    final handled = await tester.binding.handlePopRoute();
    await tester.pump();

    expect(handled, isTrue, reason: 'the shell consumed back instead of leaving the app');
    expect(home.selectedIndex, 0);
    expect(find.byType(HomePage), findsOneWidget);
    await _disposeHomePage(tester);
  });

  testWidgets('the mounted Home registers as the one shell links open into (nav #3)', (tester) async {
    await _pumpHomePage(tester);
    expect(HomeNavigation.isHomeMounted, isTrue);

    await _disposeHomePage(tester);
    expect(HomeNavigation.isHomeMounted, isFalse);
  });

  for (final (plan, expected) in [(PlanType.plus, 'paid'), (PlanType.basic, 'free'), (null, 'unknown')]) {
    testWidgets('mounted Home startup attributes survey answers to the current $expected plan', (tester) async {
      final analytics = await _mountHomeForSurvey(tester);
      final prefs = SharedPreferencesUtil();
      final uid = prefs.uid;
      _seedSurveyGap(uid);
      final usage = tester.element(find.byType(HomePage)).read<UsageProvider>();

      await _runHomeStartupPrompts(tester);
      expect(find.text(_surveyTitle), findsOneWidget);

      // The plan is read when the user answers, even if it loaded after showing the sheet.
      usage.debugSetSubscription(plan == null ? null : _surveySubscription(plan));
      await tester.pump();
      await tester.tap(find.text('Charging is a hassle'));
      await tester.pumpAndSettle();
      await AnalyticsManager.flushPending(force: true);

      expect(PendantAbsence.instance.questionShown(uid), isTrue);
      expect(analytics.answers.single, containsPair('plan', expected));
      expect(analytics.answers.single, containsPair('days_without_connection', 4));
      await _disposeHomePage(tester);
    });
  }

  for (final gate in [
    'signed-out',
    'onboarding',
    'background',
    'paired device',
    'Friend Dev Kit',
    'Omi Neo',
    'live link',
    'link opening',
  ]) {
    testWidgets('mounted Home startup suppresses the survey for $gate', (tester) async {
      final analytics = await _mountHomeForSurvey(tester);
      try {
        final prefs = SharedPreferencesUtil();
        final uid = prefs.uid;
        final device = tester.element(find.byType(HomePage)).read<DeviceProvider>();
        _seedSurveyGap(uid);
        switch (gate) {
          case 'signed-out':
            prefs.uid = '';
          case 'onboarding':
            prefs.onboardingCompleted = false;
          case 'background':
            tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
          case 'paired device':
            prefs.btDevice = _surveyPendant.copyWith(type: DeviceType.openglass);
          case 'Friend Dev Kit':
            prefs.btDevice = _surveyPendant.copyWith(name: 'Friend Dev Kit 1', modelNumber: 'Omi Device');
          case 'Omi Neo':
            prefs.btDevice = _surveyPendant.copyWith(modelNumber: 'Omi Neo');
          case 'live link':
            device.isConnected = true;
          case 'link opening':
            device.connectedDevice = _surveyPendant;
        }

        await _runHomeStartupPrompts(tester);

        expect(find.text(_surveyTitle), findsNothing);
        expect(PendantAbsence.instance.questionShown(uid), isFalse);
        expect(analytics.answers, isEmpty);
      } finally {
        await _disposeHomePage(tester);
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      }
    });
  }

  testWidgets('mounted Home drops a queued survey when the account changes', (tester) async {
    final analytics = await _mountHomeForSurvey(tester);
    try {
      final prefs = SharedPreferencesUtil();
      final originalUid = prefs.uid;
      _seedSurveyGap(originalUid);
      _seedSurveyGap('second-survey-account');
      final queue = PromptQueue.instance;
      queue.blocked = () => true;
      await _runHomeStartupPrompts(tester);
      expect(queue.pendingIds, contains('pendant-stop-question'));

      prefs.uid = 'second-survey-account';
      queue.blocked = () => false;
      queue.pump();
      await tester.pumpAndSettle();
      expect(find.text(_surveyTitle), findsNothing);
      expect(PendantAbsence.instance.questionShown(originalUid), isFalse);
      expect(PendantAbsence.instance.questionShown(prefs.uid), isFalse);
      expect(analytics.answers, isEmpty);
    } finally {
      await _disposeHomePage(tester);
    }
  });

  testWidgets('mounted Home resume checks the current account and its paired pendant', (tester) async {
    final analytics = await _mountHomeForSurvey(tester);
    final prefs = SharedPreferencesUtil();
    final initialUid = prefs.uid;
    _seedSurveyGap(initialUid);
    final home = tester.element(find.byType(HomePage));
    final device = home.read<DeviceProvider>()..connectedDevice = _surveyPendant;
    await _runHomeStartupPrompts(tester);
    expect(find.text(_surveyTitle), findsNothing);

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    device.connectedDevice = null;
    prefs.uid = 'second-survey-account';
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(find.text(_surveyTitle), findsNothing, reason: 'the first account’s gap cannot qualify the second');

    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
    prefs.uid = initialUid;
    home.read<UsageProvider>().debugSetSubscription(_surveySubscription(PlanType.plus));
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(find.text(_surveyTitle), findsOneWidget);
    await tester.tap(find.text('Other'));
    await tester.pumpAndSettle();
    await AnalyticsManager.flushPending(force: true);
    expect(PendantAbsence.instance.questionShown(initialUid), isTrue);
    expect(PendantAbsence.instance.questionShown('second-survey-account'), isFalse);
    expect(analytics.answers.single, containsPair('plan', 'paid'));
    await _disposeHomePage(tester);
  });
}

const _surveyTitle = 'Why did you stop wearing your pendant?';
final _surveyPendant = BtDevice(id: 'survey-pendant', name: 'Omi', type: DeviceType.omi, rssi: -55);

void _seedSurveyGap(String uid) {
  SharedPreferencesUtil().btDevice = _surveyPendant;
  PendantAbsence(now: () => DateTime.now().subtract(const Duration(days: 4, hours: 2))).observeAbsence(uid);
}

Future<_SurveyAnalytics> _mountHomeForSurvey(WidgetTester tester) async {
  PromptQueue.instance.reset();
  AnalyticsManager.resetForTesting();
  addTearDown(PromptQueue.instance.reset);
  addTearDown(AnalyticsManager.resetForTesting);
  tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
  PackageInfo.setMockInitialValues(
    appName: 'Omi Test',
    packageName: 'com.omi.test',
    version: '1.0.0',
    buildNumber: '1',
    buildSignature: '',
  );
  await _pumpHomePage(tester);
  final analytics = _SurveyAnalytics();
  AnalyticsManager.configure(analytics);
  await AnalyticsManager.init();
  return analytics;
}

Future<void> _runHomeStartupPrompts(WidgetTester tester) async {
  await tester.pump(const Duration(seconds: 2));
  await tester.pumpAndSettle();
}

UserSubscriptionResponse _surveySubscription(PlanType plan) => UserSubscriptionResponse(
      subscription: Subscription(plan: plan, status: SubscriptionStatus.active),
      transcriptionSecondsUsed: 0,
      transcriptionSecondsLimit: 0,
      wordsTranscribedUsed: 0,
      wordsTranscribedLimit: 0,
      insightsGainedUsed: 0,
      insightsGainedLimit: 0,
    );

class _SurveyAnalytics implements AnalyticsAdapter {
  final answers = <Map<String, Object>>[];

  @override
  bool get isInitialized => true;

  @override
  Future<void> init() async {}

  @override
  void track({required String eventName, Map<String, Object>? properties}) {
    if (eventName == 'Pendant Stop Question Answered' && properties != null) answers.add(Map.of(properties));
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

Future<void> _disposeHomePage(WidgetTester tester) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await tester.pump();
  await tester.pump(const Duration(milliseconds: 900));
}

Future<void> _pumpHomePage(WidgetTester tester) async {
  _stubPlugins();
  await installCrashlyticsRecorder();
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
    // Home embeds the conversation list; its speaker-tag card fetches through this seam, so no I/O.
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
          return '/tmp/omi-home-announcement-timer';
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
