import 'dart:convert';
import 'dart:io';
import 'dart:async';
import 'dart:developer' as developer;
import 'dart:ui' as ui;
import 'heavy_binding.dart';
import 'heavy_process_exit.dart';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:flutter_foreground_task/flutter_foreground_task.dart';
import 'package:integration_test/integration_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/http/conversation_api_contract.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/phone_call.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/action_item.dart' show ActionItemsResponse, ActionItemWithMetadata;
import 'package:omi/env/env.dart';
import 'package:omi/pages/action_items/action_items_page.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversations/conversations_page.dart';
import 'package:omi/pages/home/widgets/home_tab_switcher.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/messaging_channels_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/task_integration_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/phone_call_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/services/capture/capture_seams.dart';
import 'package:omi/services/capture/local_segment_store.dart';
import 'package:omi/services/dev_controls/addressability_catalog.dart' show OmiKeys;
import 'package:omi/services/wals/wal_service.dart';
import 'package:omi/services/wals/sync_transfer_keep_alive.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/conversation_bottom_bar.dart' show ConversationTab;
import 'package:path_provider/path_provider.dart';

import 'heavy_fixture.dart';
import 'heavy_fixture_server.dart';
import 'heavy_frame_collector.dart';
import 'production_shell.dart';

/// Profile-mode heavy-account perf harness (David 2026-10-25: "test perf more
/// reliably"). Runs on an approved physical phone via `tool/perf_sim_profile.sh`:
///
///   bash app/tool/perf_device_run.sh --device <UDID> --accept-baseline
///
/// Boundaries (see perf/README.md): the production builder shell with real
/// providers and real local stores; NOT the full app.main() boot (no Firebase,
/// no analytics network, no process-spawn timing). Auth stays untouched: the
/// fixture trusts nothing, the shell does not consult FirebaseAuth, and every
/// API call stays on the in-process loopback fixture. Frame numbers are
/// comparable across builds on the same physical device only. Simulator debug
/// is explicitly marked as scenario qualification, never profile acceptance.
void main() {
  final binding = HeavyProfileBinding();
  registerHeavyProcessExit(testsComplete: () => binding.allTestsPassed.isCompleted);
  final hostReady = Completer<void>();
  developer.registerExtension('ext.omi.heavy.start', (method, parameters) async {
    if (!hostReady.isCompleted) hostReady.complete();
    return developer.ServiceExtensionResponse.result('{"started":true}');
  });
  final collector = HeavyFrameCollector(
      onEmptyWindow: (scenario) => _rejectMeasurement(binding, 'no_engine_frames', scenario: scenario));
  final fixture = HeavyFixtureServer();
  final results = <String, Map<String, Object?>>{};
  final operationMarks = <Map<String, Object?>>[];
  void mark(String operation) {
    operationMarks.add({'operation': operation, 'vm_us': developer.Timeline.now});
    developer.Timeline.instantSync('heavy.operation', arguments: {'operation': operation});
  }

  late WalService walService;

  testWidgets('heavy_profile_scenarios', (tester) async {
    Env.init(const _HeavyEnv());
    await hostReady.future.timeout(const Duration(seconds: 30));
    final lifecycleSnapshot = _readNativeInitialLifecycle(binding);
    lifecycleSnapshot['native_app_active'] = await FlutterForegroundTask.isAppOnForeground;
    binding.reportData = {...?binding.reportData, 'heavy_lifecycle': lifecycleSnapshot};
    debugPrint('HEAVY_LIFECYCLE ${jsonEncode(lifecycleSnapshot)}');
    final idleFrames = await _verifyIdleScheduling(tester, binding);
    const simulatorQualification = bool.fromEnvironment('PERF_SIM_QUALIFICATION');
    const virtualQualification = bool.fromEnvironment('PERF_VIRTUAL_QUALIFICATION');
    expect(kProfileMode || (kDebugMode && simulatorQualification), isTrue,
        reason: 'Profile required; debug simulator runs must opt into qualification only');
    final resumed = await _awaitCondition(() => binding.lifecycleState == AppLifecycleState.resumed,
        timeout: const Duration(seconds: 15));
    final nativeActive = await FlutterForegroundTask.isAppOnForeground;
    final foregroundSnapshot = {
      'binding': binding.lifecycleState?.name,
      'native_buffered': ui.PlatformDispatcher.instance.initialLifecycleState,
      'native_app_active': nativeActive,
    };
    binding.reportData = {...?binding.reportData, 'heavy_foreground': foregroundSnapshot};
    debugPrint('HEAVY_FOREGROUND ${jsonEncode(foregroundSnapshot)}');
    if (!resumed || !nativeActive) _rejectMeasurement(binding, 'not_resumed', scenario: 'preflight');
    expect(resumed && nativeActive, isTrue,
        reason: 'HEAVY_FOREGROUND_REJECTED: DEV app must be natively active and resumed before fixture I/O');
    final storage = await isolateHeavyStorage();
    debugPrint('HEAVY_STAGE storage isolated');

    await fixture.start();
    Env.overrideApiBaseUrl(fixture.baseUrl!);
    HttpOverrides.global = _LoopbackOnly(Uri.parse(fixture.baseUrl!));
    addTearDown(() async {
      HttpOverrides.global = null;
      Env.clearApiBaseUrlOverrideForTesting();
      await fixture.stop();
    });
    expect(
        [Env.posthogApiKey, Env.intercomAppId, Env.intercomIOSApiKey, Env.intercomAndroidApiKey]
            .every((key) => key == null || key.isEmpty),
        isTrue,
        reason: 'Heavy harness requires local_dev without external analytics credentials');

    // 1. Seed the heavy account: preferences cache + WAL index + audio files.
    await seedHeavyPreferences();
    debugPrint('HEAVY_STAGE preferences seeded');
    // The production boot sequence initializes platform services (package
    // info + device-id hash in HTTP headers) before any provider fetches.
    await PlatformManager.initializeServices();
    final walFileCount = await seedHeavyWals();
    debugPrint('HEAVY_STAGE WALs seeded');

    // 3. The real WAL machinery over the seeded 6.5k-record index: cold-start
    // load, flush ticks, admission pressure and lifecycle drains all run.
    walService = WalService();
    var stopped = true;
    addTearDown(() async {
      if (!stopped) await walService.stop();
      collector.dispose();
    });

    final conversations = createProductionConversationProvider(isSignedIn: () => true);

    // The Home shell's conversations page self-fetches on first build
    // (requestInitialLoad defaults true): request → empty server page →
    // cache restore of the full seeded history. That whole path, plus the
    // shell mount, is the cold-start window.
    final entry = _HeavyHomeShell(conversationsProvider: conversations, walService: walService);

    const timelineEnabled = bool.fromEnvironment('PERF_HEAVY_TIMELINE');
    if (timelineEnabled) await binding.enableTimeline(streams: const ['Dart', 'GC']);
    await (() async {
      // 4. Cold start: shell mount → Home request → empty server page → cache
      //    decode of the full seeded history → grouped list rendered → settled.
      collector.begin('cold_start');
      mark('cold_start.mount');
      walService.start();
      stopped = false;
      await tester.pumpWidget(entry);
      await _awaitCondition(() => globalNavigatorKey.currentContext != null, timeout: const Duration(seconds: 10));
      expect(globalNavigatorKey.currentContext, isNotNull);
      await walService.syncs.phone.walReady;
      await globalNavigatorKey.currentContext!.read<SyncProvider>().initialized;
      await _awaitCondition(
          () => globalNavigatorKey.currentContext!.read<SyncProvider>().allWals.length == heavyWalCount,
          timeout: const Duration(seconds: 15));
      expect(globalNavigatorKey.currentContext!.read<SyncProvider>().allWals.length, heavyWalCount,
          reason: 'Home must observe the real heavy WAL inventory');
      final settled = await _awaitCondition(
          () => conversations.conversations.length >= heavyConversationCount && !conversations.isLoadingConversations,
          timeout: const Duration(seconds: 30));
      expect(settled, isTrue, reason: 'Home must restore the complete synthetic conversation history');
      mark('cold_start.cache_ready');
      await _idle(const Duration(seconds: 3));
      var summary = await collector.end();
      summary['restored_from_cache'] = settled;
      results['cold_start'] = summary;
      debugPrint('HEAVY_STAGE cold_start complete');

      // 5. Scroll the conversations list: real flings over the full history.
      collector.begin('scroll_conversations');
      final listFinder = await _verticalScrollable(tester, find.byType(ConversationsPage));
      for (var i = 0; i < 8; i++) {
        mark('scroll_conversations.fling.$i');
        await tester.fling(listFinder, Offset(0, i < 4 ? -600 : 600), 2500);
        await _settleScrolled();
        await _idle(const Duration(milliseconds: 500));
      }
      results['scroll_conversations'] = await collector.end();
      debugPrint('HEAVY_STAGE scroll complete');

      // 6. Open the newest conversation's detail page and scroll its transcript.
      collector.begin('open_conversation');
      final newest = conversations.conversations.first;
      mark('open_conversation.push');
      globalNavigatorKey.currentState!.push(MaterialPageRoute<void>(
          builder: (_) => ConversationDetailPage(conversation: newest, initialTab: ConversationTab.transcript)));
      await _idle(const Duration(seconds: 2));
      final transcriptFinder = await _verticalScrollable(tester, find.byType(ConversationDetailPage));
      for (var i = 0; i < 6; i++) {
        mark('open_conversation.fling.$i');
        await tester.fling(transcriptFinder, Offset(0, i < 3 ? -600 : 600), 2500);
        await _settleScrolled();
        await _idle(const Duration(milliseconds: 400));
      }
      globalNavigatorKey.currentState!.pop();
      mark('open_conversation.pop');
      await _idle(const Duration(seconds: 1));
      results['open_conversation'] = await collector.end();
      debugPrint('HEAVY_STAGE detail complete');

      // 7. Home ↔ Tasks tab switches on the production switch shape.
      collector.begin('tab_switch');
      for (var i = 0; i < 8; i++) {
        mark('tab_switch.tasks.$i');
        await tester.tap(find.byKey(OmiKeys.homeTabTasks));
        await _idle(const Duration(milliseconds: 700));
        mark('tab_switch.home.$i');
        await tester.tap(find.byKey(OmiKeys.homeTabHome));
        await _idle(const Duration(milliseconds: 700));
      }
      results['tab_switch'] = await collector.end();
      debugPrint('HEAVY_STAGE tabs complete');

      // 8. Background/foreground cycles while the WAL service runs its real
      //    pause/resume work over the 6.5k-record backlog.
      collector.begin('wal_sync_bg_fg');
      await walService.syncs.phone.walReady;
      final sync = globalNavigatorKey.currentContext!.read<SyncProvider>().syncWals();
      final uploading = await _awaitCondition(() => fixture.countsByKind.containsKey('/v2/sync-local-files'),
          timeout: const Duration(seconds: 15));
      expect(uploading, isTrue, reason: 'lifecycle window must overlap a real loopback WAL upload');
      for (var i = 0; i < 3; i++) {
        expect(fixture.activeUploads, greaterThan(0), reason: 'Each lifecycle cycle must overlap the upload');
        binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
        binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
        binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
        await _idle(const Duration(seconds: 2));
        binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
        binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
        binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
        await _idle(const Duration(seconds: 2));
        await tester.fling(listFinder, const Offset(0, -400), 1500);
        await _settleScrolled();
        await _idle(const Duration(milliseconds: 500));
      }
      results['wal_sync_bg_fg'] = await collector.end();
      await sync;
    })();

    // 9. Receipt: engine frame statistics per scenario.
    final receipt = <String, Object?>{
      'schema': 'omi-mobile-perf-sim/v2',
      'frame_policy': 'framework-requested/v1',
      'idle_preflight_frames': idleFrames,
      'pacing': 'fixed-real-time/v1',
      'build_mode': kProfileMode ? 'profile' : 'debug',
      'device_os_version': Platform.operatingSystemVersion,
      'acceptance_eligible': kProfileMode && !simulatorQualification && !virtualQualification && !timelineEnabled,
      'virtual_qualification': virtualQualification,
      'timeline_enabled': timelineEnabled,
      'storage_isolated': true,
      'foreground_before_measurement': resumed,
      'native_foreground_before_measurement': nativeActive,
      'flavor': 'dev',
      'scenario_order': collector.windowOrder,
      'dataset': {
        'conversations': heavyConversationCount,
        'detail_segments': heavyDetailSegments,
        'wals': heavyWalCount,
        'wal_files': walFileCount,
        'people': 40,
        'task_items': 50,
      },
      'fixture_requests': fixture.countsByKind,
      'operation_marks': operationMarks,
      'scenarios': results,
      'complete': results.length == 5,
    };
    binding.reportData = {...?binding.reportData, 'heavy_profile': receipt};

    // The runner also fishes this out of the app container; the driver
    // response remains the primary transport.
    try {
      final directory = await getApplicationDocumentsDirectory();
      final file = File('${directory.path}/heavy_profile_receipt.json');
      await file.writeAsString(const JsonEncoder.withIndent('  ').convert(receipt), flush: true);
      debugPrint('PERF_RECEIPT_FILE=${file.path}');
    } catch (error) {
      debugPrint('PERF_RECEIPT_FILE=unavailable: $error');
    }

    await walService.stop();
    stopped = true;
    await fixture.stop();
    collector.dispose();
    await tester.pumpWidget(const SizedBox.shrink());
    // Leave fixture files intact for inspection. No audio cleanup is run here.
    debugPrint('HEAVY_FIXTURE_STORAGE=${storage.path}');
    expect(results['cold_start']!['restored_from_cache'], isTrue,
        reason: 'Home must restore the seeded history from the conversations cache');
  }, timeout: const Timeout(Duration(minutes: 12)));
}

Map<String, Object?> _readNativeInitialLifecycle(IntegrationTestWidgetsFlutterBinding binding) {
  final before = binding.lifecycleState?.name;
  // TestPlatformDispatcher deliberately defaults its initial state to ''. Use
  // the actual embedder buffer once, rather than inventing a resumed event.
  // Subsequent real lifecycle events remain authoritative.
  final native = ui.PlatformDispatcher.instance.initialLifecycleState;
  if (binding.lifecycleState == null && native.isNotEmpty) {
    binding.platformDispatcher.initialLifecycleStateTestValue = native;
    binding.readTestInitialLifecycleStateFromNativeWindow();
  }
  return {'binding_before': before, 'native_buffered': native, 'binding_after_read': binding.lifecycleState?.name};
}

Future<int> _verifyIdleScheduling(WidgetTester tester, HeavyProfileBinding binding) async {
  await tester.pumpWidget(const SizedBox.shrink());
  await _idle(const Duration(milliseconds: 1200));
  var frames = 0;
  void count(List<ui.FrameTiming> timings) => frames += timings.length;
  binding.addTimingsCallback(count);
  try {
    await _idle(const Duration(seconds: 2));
  } finally {
    binding.removeTimingsCallback(count);
  }
  debugPrint('HEAVY_IDLE_PREFLIGHT frames=$frames');
  expect(frames, lessThanOrEqualTo(3), reason: 'Idle test-framework frames must not dilute real UI percentiles');
  return frames;
}

void _rejectMeasurement(IntegrationTestWidgetsFlutterBinding binding, String reason, {required String scenario}) {
  binding.reportData = {
    ...?binding.reportData,
    'heavy_measurement_rejection': {
      'kind': 'foreground_or_frames',
      'reason': reason,
      'scenario': scenario,
      'binding_lifecycle': binding.lifecycleState?.name,
    }
  };
}

class _LoopbackOnly extends HttpOverrides {
  _LoopbackOnly(this.authority);
  final Uri authority;
  @override
  HttpClient createHttpClient(SecurityContext? context) {
    final client = super.createHttpClient(context);
    client.connectionFactory = (uri, proxyHost, proxyPort) {
      // IntegrationTest's VM-service connection is also loopback, on its own
      // ephemeral port. External API/DNS/proxy destinations remain blocked.
      final loopback = uri.host == 'localhost' || InternetAddress.tryParse(uri.host)?.isLoopback == true;
      if (proxyHost != null || uri.scheme != 'http' || !loopback) {
        return Future.error(const SocketException('Heavy fixture blocked a non-fixture HTTP request'));
      }
      return Socket.startConnect(uri.host, uri.port);
    };
    return client;
  }
}

/// No generated environment or analytics credentials enter fixture bootstrap.
class _HeavyEnv implements EnvFields {
  const _HeavyEnv();
  @override
  String? get apiBaseUrl => null;
  @override
  String? get posthogApiKey => null;
  @override
  String? get intercomAppId => null;
  @override
  String? get intercomIOSApiKey => null;
  @override
  String? get intercomAndroidApiKey => null;
  @override
  String? get googleClientId => null;
  @override
  String? get googleClientSecret => null;
  @override
  bool get useWebAuth => false;
  @override
  bool get useAuthCustomToken => false;
}

/// Real-time condition wait: pump nothing while waiting — the live binding
/// renders frames on its own, which is exactly what the collector observes.
Future<bool> _awaitCondition(bool Function() condition, {required Duration timeout}) async {
  final deadline = DateTime.now().add(timeout);
  while (DateTime.now().isBefore(deadline)) {
    if (condition()) return true;
    await _idle(const Duration(milliseconds: 100));
  }
  return condition();
}

Future<void> _idle(Duration duration) => Future<void>.delayed(duration);

// Production tickers may never settle. A fixed real-time pause keeps the same
// scripted duration in every run without manufacturing WidgetTester frames.
Future<void> _settleScrolled() => _idle(const Duration(seconds: 2));

Future<Finder> _verticalScrollable(WidgetTester tester, Finder scope) async {
  final candidates = find.descendant(
    of: scope,
    matching: find.byWidgetPredicate(
        (widget) => widget is Scrollable && axisDirectionToAxis(widget.axisDirection) == Axis.vertical),
  );
  bool hasExtent(Element element) {
    final state = (element as StatefulElement).state;
    return state is ScrollableState && state.position.maxScrollExtent > 0;
  }

  await _awaitCondition(() => candidates.evaluate().any(hasExtent), timeout: const Duration(seconds: 10));
  final withExtent = candidates.evaluate().where(hasExtent);
  expect(withExtent, isNotEmpty, reason: 'scenario page must expose scrollable seeded content');
  final element = withExtent.first;
  return find.byElementPredicate((candidate) => identical(candidate, element));
}

/// The Home surface under measurement: the two production tabs with the
/// production switch shape ([HomeTabSwitcher] driving [HomeProvider], an
/// [IndexedStack] whose slots stay stable, tickers gated to the selected tab).
class _HeavyHomeShell extends StatelessWidget {
  const _HeavyHomeShell({required this.conversationsProvider, required this.walService});

  final ConversationProvider conversationsProvider;
  final WalService walService;

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider<ConversationProvider>.value(value: conversationsProvider),
        ChangeNotifierProvider(create: (_) => HomeProvider()),
        ChangeNotifierProvider<CaptureProvider>(create: (_) => _HarnessCapture(walService: walService)),
        ChangeNotifierProvider<DeviceProvider>(create: (_) => _NoDevice()),
        ChangeNotifierProvider<PhoneCallProvider>(create: (_) => _NoPhoneCall()),
        ChangeNotifierProvider(
            create: (_) => SpeakerTagPromptsProvider(
                  fetchPrompts: () async => const ApiSuccess(GeneratedSpeakerTagPromptsResponse()),
                )),
        ChangeNotifierProvider(create: (_) => MemoriesProvider()),
        ChangeNotifierProvider(create: (_) => PeopleProvider()),
        ChangeNotifierProvider(create: (_) => MessageProvider()),
        ChangeNotifierProvider(create: (_) => LocalRecordingsProvider(ledger: walService.syncs.phone)),
        ListenableProvider(create: (_) => ConnectivityProvider()),
        ListenableProvider(create: (_) => AppProvider()),
        ChangeNotifierProvider(create: (_) => UsageProvider()),
        ChangeNotifierProvider(
            create: (_) => SyncProvider(
                  walService: walService,
                  startBackgroundSync: false,
                  keepAlive: SyncTransferKeepAlive(start: () async {}, stop: () async {}),
                )),
        ChangeNotifierProvider(create: (_) => IntegrationProvider()),
        ChangeNotifierProvider(create: (_) => MessagingChannelsProvider(readConfig: () async => ChatAppsConfig.off)),
        ChangeNotifierProvider(create: (_) => FolderProvider()),
        ChangeNotifierProvider(create: (_) => VoiceRecorderProvider()),
        ChangeNotifierProxyProvider2<AppProvider, ConversationProvider, ConversationDetailProvider>(
          create: (_) => ConversationDetailProvider(),
          update: (_, app, conversations, previous) => previous!..setProviders(app, conversations),
        ),
        ChangeNotifierProvider(
          create: (_) => ActionItemsProvider(
              getActionItems: (
                      {limit = 50,
                      offset = 0,
                      completed,
                      conversationId,
                      startDate,
                      endDate,
                      dueStartDate,
                      dueEndDate}) async =>
                  ActionItemsResponse(actionItems: [
                    for (var i = 0; i < 50; i++)
                      ActionItemWithMetadata(
                        id: 'perf-item-$i',
                        completed: false,
                        description: 'Heavy fixture action item $i: deterministic task text for the tasks tab.',
                        createdAt: DateTime.now().subtract(Duration(hours: i)),
                      )
                  ], hasMore: false)),
        ),
        ChangeNotifierProvider(create: (_) => TaskIntegrationProvider(fetchStatus: () async => null)),
        ChangeNotifierProvider(create: (_) => GoalsProvider(goalsFetcher: () async => [])),
      ],
      // Providers sit outside the shell so pushed routes (conversation detail)
      // resolve them exactly like MyApp's provider scope does.
      child: const PerfProductionShell(page: _HeavyHomeTabs()),
    );
  }
}

class _HeavyHomeTabs extends StatefulWidget {
  const _HeavyHomeTabs();

  @override
  State<_HeavyHomeTabs> createState() => _HeavyHomeTabsState();
}

class _HeavyHomeTabsState extends State<_HeavyHomeTabs> {
  final List<Widget?> _pages = List<Widget?>.filled(HomeProvider.tabCount, null);
  @override
  Widget build(BuildContext context) {
    final selected = context.select<HomeProvider, int>((home) => home.selectedIndex);
    _pages[selected] ??= selected == HomeProvider.homeTab
        ? ConversationsPage(loadRecaps: () async => (items: <DailySummary>[], ok: true))
        : const ActionItemsPage();
    return Scaffold(
      backgroundColor: Colors.black,
      body: Column(
        children: [
          const SizedBox(height: 59),
          HomeTabSwitcher(
            onTabTap: (index, isRepeat) => context.read<HomeProvider>().setIndex(index),
          ),
          Expanded(
            child: IndexedStack(
              index: selected,
              children: [
                for (var index = 0; index < _pages.length; index++)
                  TickerMode(
                    enabled: index == selected,
                    child: _pages[index] ?? const SizedBox.shrink(),
                  ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

/// The capture provider Home reads, composed like the seeded perf world's
/// live capture: production provider with the external I/O boundaries
/// injected, but bound to the harness's real WAL service so the seeded
/// backlog drives the real machinery. No device, no native recorder.
class _HarnessCapture extends CaptureProvider {
  _HarnessCapture({required WalService walService})
      : super(
          walService: walService,
          connectivity: CaptureConnectivityBoundary(
              initiallyConnected: true, changes: const Stream.empty(), isConnected: () => true),
          bleListeners: _HarnessBle(),
          inProgressConversationLoader: () async {},
          localSegmentStore: LocalSegmentStore.disabled(),
        );
}

class _HarnessBle implements CaptureBleListeners {
  @override
  void addBatchRecordingFinalizedListener(void Function(String) callback) {}

  @override
  void removeBatchRecordingFinalizedListener(void Function(String) callback) {}
}

/// Hardware boundaries only; Home still renders its production capture widget.
class _NoDevice extends ChangeNotifier implements DeviceProvider {
  @override
  bool get havingNewFirmware => false;
  @override
  BtDevice? get pairedDevice => null;
  @override
  bool get isConnected => false;
  @override
  BtDevice? get connectedDevice => null;
  @override
  bool get isConnecting => false;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _NoPhoneCall extends ChangeNotifier implements PhoneCallProvider {
  @override
  PhoneCallState get callState => PhoneCallState.idle;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}
