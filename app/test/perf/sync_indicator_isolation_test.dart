import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/pending_work.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart' show RateLimitReason;
import 'package:omi/pages/home/widgets/battery_info_widget.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/pages/settings/device/device_live_sections.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/ui/components/omi_live_indicators.dart';

class _Device extends ChangeNotifier implements DeviceProvider {
  final device = BtDevice(id: 'omi-perf', name: 'Omi', type: DeviceType.omi, rssi: -40);
  @override
  BtDevice? get connectedDevice => device;
  @override
  BtDevice? get pairedDevice => null; // No BLE feature discovery in a hermetic test.
  @override
  bool get isConnected => true;
  @override
  bool get isConnecting => false;
  @override
  int get batteryLevel => 75;
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

class _Capture extends ChangeNotifier implements CaptureProvider {
  @override
  bool get pendantCaptureActionRequired => false;
  @override
  bool get pendantCaptureVerified => true;
  @override
  bool get pendantReconnectInFlight => false;
  bool streaming = false;
  bool paused = false;
  double rate = 1;
  @override
  BtDevice? get recordingDevice => null;
  @override
  double get bleReceiveRateKbps => rate;
  @override
  double get wsSendRateKbps => rate;
  @override
  String? get liveCaptureSource => streaming ? 'omi' : null;
  @override
  bool get isPaused => paused;
  @override
  bool get havingRecordingDevice => streaming;
  @override
  List<TranscriptSegment> get segments => const [];
  @override
  DateTime? get liveCaptureStartedAt => null;
  @override
  void addMetricsListener() {}
  @override
  void removeMetricsListener() {}
  void tick() {
    rate++;
    notifyListeners();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Sync extends ChangeNotifier implements SyncProvider {
  bool active = false;
  @override
  SyncState get syncState => active ? const SyncState(status: SyncStatus.syncing) : const SyncState();
  @override
  bool get isSyncing => active;
  @override
  List<Wal> get allWals {
    inventoryReads++;
    return wals;
  }

  int inventoryReads = 0;
  final wals = <Wal>[];
  @override
  int get missingWalsInSeconds => 0;
  // The device card's status line reads the rate-limit state; this fake is never limited.
  @override
  bool get isRateLimited => false;
  @override
  RateLimitReason? get rateLimitReason => null;
  void tick() => notifyListeners();
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _PaintCounter extends CustomPainter {
  int paints = 0;
  @override
  void paint(Canvas canvas, Size size) => paints++;
  @override
  bool shouldRepaint(_PaintCounter oldDelegate) => false;
}

Widget _app(Widget child, _Device device, _Capture capture, _Sync sync, {bool reduceMotion = false}) => MultiProvider(
      providers: [
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
        ChangeNotifierProvider<SyncProvider>.value(value: sync),
        ChangeNotifierProvider(create: (_) => HomeProvider()),
      ],
      child: MaterialApp(
        theme: ThemeData.dark(),
        builder: (context, child) => MediaQuery(
          data: MediaQuery.of(context).copyWith(disableAnimations: reduceMotion),
          child: child!,
        ),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: RepaintBoundary(key: const Key('evidence'), child: child),
      ),
    );

Future<void> _sampleFrame(WidgetTester tester, List<double> uiMs) async {
  tester.binding.scheduleFrameCallback((_) {
    final watch = Stopwatch()..start();
    tester.binding.addPostFrameCallback((_) {
      uiMs.add(watch.elapsedMicroseconds / 1000);
    });
  });
  await tester.pump(const Duration(microseconds: 16667));
}

String _timing(List<double> ms) {
  final sorted = [...ms]..sort();
  return 'hostUiMs p50=${sorted[(sorted.length * .5).ceil() - 1].toStringAsFixed(3)} '
      'p95=${sorted[(sorted.length * .95).ceil() - 1].toStringAsFixed(3)}';
}

// Optional local screenshots; ordinary CI tests do no filesystem I/O.
Future<void> _screenshot(WidgetTester tester, String name) async {
  final directory = Platform.environment['SYNC_INDICATOR_EVIDENCE_DIR'];
  if (directory == null) return;
  final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(const Key('evidence')));
  final image = await boundary.toImage(pixelRatio: 1);
  final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
  await tester.runAsync(() async {
    await Directory(directory).create(recursive: true);
    await File('$directory/$name.png').writeAsBytes(bytes!.buffer.asUint8List());
  });
  image.dispose();
}

void main() {
  final store = PendingWorkStore(
    loadPending: () async => const ApiSuccess(PendingWorkSnapshot.disabled),
    loadAttention: () async => const ApiSuccess(AttentionItemsPage.disabled),
  );
  final previousStore = PendingWorkStore.instance;
  setUpAll(() => PendingWorkStore.instance = store);
  tearDownAll(() {
    PendingWorkStore.instance = previousStore;
    store.dispose();
  });
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  for (final syncing in [false, true]) {
    testWidgets('Home header isolates animation while syncing=$syncing', (tester) async {
      final device = _Device();
      final capture = _Capture();
      final sync = _Sync()..active = syncing;
      addTearDown(device.dispose);
      addTearDown(capture.dispose);
      addTearDown(sync.dispose);
      final paint = _PaintCounter();
      await tester.pumpWidget(_app(
        Scaffold(
            appBar: AppBar(leadingWidth: 180, leading: CustomPaint(painter: paint, child: const BatteryInfoWidget()))),
        device,
        capture,
        sync,
      ));
      await tester.pump(const Duration(seconds: 1));
      final builds = <String, int>{};
      final previous = debugOnRebuildDirtyWidget;
      debugOnRebuildDirtyWidget = (element, builtOnce) {
        final name = element.widget.runtimeType.toString();
        builds.update(name, (n) => n + 1, ifAbsent: () => 1);
        previous?.call(element, builtOnce);
      };
      addTearDown(() => debugOnRebuildDirtyWidget = previous);
      await _screenshot(tester, 'home-syncing-$syncing');
      paint.paints = 0;
      final uiMs = <double>[];
      for (var frame = 0; frame < 60; frame++) {
        await _sampleFrame(tester, uiMs);
      }
      debugPrint(_timing(uiMs));
      debugPrint('HOME syncing=$syncing frames=60 surroundingPaints=${paint.paints} rebuilds=$builds');
      expect(builds, isEmpty, reason: 'Animation must repaint without rebuilding any widgets.');
      expect(paint.paints, 0, reason: 'The ring must not repaint the Home header.');
      await tester.pumpWidget(const SizedBox.shrink());
    });

    testWidgets('Device ignores irrelevant provider ticks while syncing=$syncing', (tester) async {
      final device = _Device();
      final capture = _Capture()..streaming = true;
      final sync = _Sync()..active = syncing;
      addTearDown(device.dispose);
      addTearDown(capture.dispose);
      addTearDown(sync.dispose);
      await tester.pumpWidget(_app(const DeviceSettings(), device, capture, sync));
      await tester.pump(const Duration(seconds: 1));
      final builds = <String, int>{};
      final previous = debugOnRebuildDirtyWidget;
      debugOnRebuildDirtyWidget = (element, builtOnce) {
        final name = element.widget.runtimeType.toString();
        builds.update(name, (n) => n + 1, ifAbsent: () => 1);
        previous?.call(element, builtOnce);
      };
      addTearDown(() => debugOnRebuildDirtyWidget = previous);
      await _screenshot(tester, 'device-syncing-$syncing');
      sync.inventoryReads = 0;
      final uiMs = <double>[];
      for (var frame = 0; frame < 60; frame++) {
        // A repeatable stress rate; production metrics are 0.2 Hz, sync callbacks can burst.
        if (frame % 6 == 0) {
          capture.tick();
          sync.tick();
        }
        await _sampleFrame(tester, uiMs);
      }
      debugPrint(_timing(uiMs));
      debugPrint('DEVICE syncing=$syncing frames=60 providerTicks=10 pageBuilds=${builds['DeviceSettings'] ?? 0}');
      expect(builds['DeviceSettings'] ?? 0, 0,
          reason: 'Metrics/progress with unchanged visible values must stay local.');
      expect(sync.inventoryReads, 10, reason: 'Stats and Right now must share one inventory pass per sync update.');
      sync.inventoryReads = 0;
      capture.tick();
      await tester.pump();
      expect(sync.inventoryReads, 0, reason: 'Capture metrics must not rescan recording history.');
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }

  for (final surface in ['home', 'device']) {
    testWidgets('still visual $surface with sync active', (tester) async {
      final device = _Device();
      final capture = _Capture()..streaming = true;
      final sync = _Sync()..active = true;
      addTearDown(device.dispose);
      addTearDown(capture.dispose);
      addTearDown(sync.dispose);
      sync.wals.add(Wal(
          timerStart: 1, codec: BleAudioCodec.opus, seconds: 600, status: WalStatus.miss, storage: WalStorage.sdcard));
      await tester.pumpWidget(_app(
        surface == 'device'
            ? const DeviceSettings()
            : Scaffold(appBar: AppBar(leadingWidth: 180, leading: const BatteryInfoWidget())),
        device,
        capture,
        sync,
        reduceMotion: true,
      ));
      await tester.pumpAndSettle();
      await _screenshot(tester, '$surface-still');
      expect(tester.takeException(), isNull);
      await tester.pumpWidget(const SizedBox.shrink());
    });
  }

  testWidgets('arc repaints without repainting its static glyph', (tester) async {
    final glyph = _PaintCounter();
    await tester.pumpWidget(MaterialApp(
        home: Center(
            child: OmiActivityRing(
      active: true,
      child: CustomPaint(painter: glyph, size: const Size.square(16)),
    ))));
    await tester.pump();
    final boundary = tester.renderObject<RenderRepaintBoundary>(find.descendant(
      of: find.byType(OmiActivityRing),
      matching: find.byType(RepaintBoundary),
    ));
    int arcPaints() => boundary.debugAsymmetricPaintCount + boundary.debugSymmetricPaintCount;
    final before = arcPaints();
    glyph.paints = 0;
    await tester.pump(const Duration(milliseconds: 100));
    expect(arcPaints(), greaterThan(before), reason: 'The arc must actually animate.');
    expect(glyph.paints, 0);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('Device still updates pause state and sync amounts', (tester) async {
    final device = _Device();
    final capture = _Capture()..streaming = true;
    final sync = _Sync()..active = true;
    addTearDown(device.dispose);
    addTearDown(capture.dispose);
    addTearDown(sync.dispose);
    await tester.pumpWidget(_app(const DeviceSettings(), device, capture, sync));
    await tester.pump();
    expect(find.text('Listening · Connected'), findsOneWidget);
    capture.paused = true;
    capture.tick();
    await tester.pump();
    expect(find.text('Paused · Connected'), findsOneWidget);
    sync.wals.add(Wal(
        timerStart: 1, codec: BleAudioCodec.opus, seconds: 600, status: WalStatus.miss, storage: WalStorage.sdcard));
    sync.tick();
    await tester.pump();
    expect(find.byKey(const Key('device_right_now_catching_up')), findsOneWidget);
    expect(tester.widget<DeviceRightNowGroup>(find.byType(DeviceRightNowGroup)).catchingUp?.status, isNotEmpty);
    expect(tester.widget<DeviceStatsRow>(find.byType(DeviceStatsRow)).onDeviceSeconds, 600);
    sync.active = false;
    sync.tick();
    await tester.pump();
    expect(find.byKey(const Key('device_right_now_catching_up')), findsOneWidget,
        reason: 'A waiting backlog remains reachable after a transfer stops.');
    sync.wals.clear();
    sync.tick();
    await tester.pump();
    expect(find.byKey(const Key('device_right_now_catching_up')), findsNothing);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('ring stops scheduling frames when idle, muted or under Reduce Motion', (tester) async {
    Future<void> show({bool active = true, bool visible = true, bool reduceMotion = false}) => tester.pumpWidget(
          MaterialApp(
              home: MediaQuery(
            data: MediaQueryData(disableAnimations: reduceMotion),
            child:
                TickerMode(enabled: visible, child: OmiActivityRing(active: active, child: const Icon(Icons.circle))),
          )),
        );
    await show();
    await tester.pump(const Duration(milliseconds: 100));
    expect(tester.binding.transientCallbackCount, greaterThan(0));
    for (final state in [(false, true, false), (true, false, false), (true, true, true)]) {
      await show(active: state.$1, visible: state.$2, reduceMotion: state.$3);
      await tester.pump();
      expect(tester.binding.transientCallbackCount, 0);
    }
    await show();
    await tester.pump(const Duration(milliseconds: 100));
    expect(tester.binding.transientCallbackCount, greaterThan(0));
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
