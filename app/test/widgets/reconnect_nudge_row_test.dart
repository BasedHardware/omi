import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/widgets/reconnect_nudge_row.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/services/devices/device_last_connected.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/widgets/bluetooth_guidance_listener.dart';

final _now = DateTime.utc(2026, 10, 26, 18);
final _omi = BtDevice(id: 'omi-1', name: 'Omi', type: DeviceType.omi, rssi: -50, firmwareRevision: '3.0.21');
const _row = Key('reconnect_nudge_row');
const _reconnect = Key('reconnect_nudge_reconnect');
const _close = Key('reconnect_nudge_close');

class _FakeDeviceProvider extends ChangeNotifier implements DeviceProvider {
  _FakeDeviceProvider({this.reconnects = false, this.slow = false});

  /// Whether Reconnect brings the Omi back.
  final bool reconnects;

  /// Whether an attempt waits for [finish] instead of ending at once.
  final bool slow;
  Completer<void>? _attempt;
  int connectCalls = 0;

  @override
  BtDevice? pairedDevice;
  @override
  BtDevice? connectedDevice;
  @override
  bool isConnecting = false;
  @override
  bool isConnected = false;

  void connect() {
    connectedDevice = _omi;
    pairedDevice = _omi;
    isConnected = true;
    notifyListeners();
  }

  /// Ends a slow attempt; [connected] lands the Omi first.
  void finish({bool connected = false}) {
    if (connected) connect();
    _attempt?.complete();
  }

  @override
  Future scanAndConnectToDevice() {
    connectCalls++;
    if (slow) return (_attempt = Completer<void>()).future;
    if (reconnects) connect();
    return Future.value();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _RecordingAnalytics implements AnalyticsAdapter {
  final events = <(String, Map<String, Object>)>[];

  @override
  bool get isInitialized => true;
  @override
  Future<void> init() async {}
  @override
  void track({required String eventName, Map<String, Object>? properties}) =>
      events.add((eventName, properties ?? const {}));
  @override
  void alias({required String newUserId}) {}
  @override
  void identify({required String userId, Map<String, Object>? userProperties}) {}
  @override
  void setInteractionContext({String? screenName, required String target}) {}
  @override
  void registerSuperProperties(Map<String, Object> properties) {}
  @override
  void enable() {}
  @override
  void disable() {}
  @override
  void reset() {}

  List<(String, Map<String, Object>)> named(String prefix) => [
        for (final e in events)
          if (e.$1.startsWith(prefix)) e,
      ];
}

/// Bluetooth on and allowed.
BluetoothReadiness _ready() =>
    BluetoothReadiness(readState: () async => 'on', permissionState: (_) async => null, observeBridge: false);

/// Stored state of a phone whose Omi last connected [daysAgo] days before [_now].
Future<void> _seed({BtDevice? device, double? daysAgo, DateTime? dismissedAt}) async {
  final prefs = SharedPreferencesUtil();
  for (final key in ['btDevice', 'btDevices', 'deviceLastConnectedAt', 'reconnectNudgeDismissedAt']) {
    await prefs.remove(key);
  }
  if (device != null) await prefs.btDeviceSet(device);
  if (daysAgo != null) DeviceLastConnected.mark(_now.subtract(Duration(minutes: (daysAgo * 24 * 60).round())));
  if (dismissedAt != null) ReconnectNudge.markClosed(dismissedAt);
}

/// Home with the row. [clock] is what the row reads as now; tests move it with the fake timers.
/// [homeVisible] stands in for Home's tab being shown. The app's Bluetooth prompt is mounted the
/// way main.dart mounts it.
Future<void> _pump(
  WidgetTester tester,
  _FakeDeviceProvider provider, {
  DateTime Function()? clock,
  List<BuildContext>? guideOpens,
  BluetoothReadiness? readiness,
  ValueListenable<bool>? homeVisible,
  double textScale = 1,
}) async {
  // iPhone 17 Pro, so widths and wrapping match the device.
  tester.view
    ..physicalSize = const Size(402 * 3, 874 * 3)
    ..devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  final bluetooth = readiness ?? _ready();
  final navigatorKey = GlobalKey<NavigatorState>();
  Widget row = ReconnectNudgeRow(
    now: clock ?? () => _now,
    readiness: bluetooth,
    openGuide: (context) async => guideOpens?.add(context),
  );
  if (homeVisible != null) {
    final child = row;
    row = ValueListenableBuilder<bool>(
        valueListenable: homeVisible, builder: (_, visible, __) => TickerMode(enabled: visible, child: child));
  }
  await tester.pumpWidget(
    MaterialApp(
      navigatorKey: navigatorKey,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      builder: (context, child) =>
          BluetoothGuidanceListener(readiness: bluetooth, navigatorKey: navigatorKey, child: child!),
      home: MediaQuery(
        data: MediaQueryData(size: const Size(402, 874), textScaler: TextScaler.linear(textScale)),
        child: ChangeNotifierProvider<DeviceProvider>.value(value: provider, child: Scaffold(body: row)),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  late _RecordingAnalytics analytics;

  setUp(() async {
    ReconnectNudgeRow.resetShownForTesting();
    AnalyticsManager.resetForTesting();
    SharedPreferences.setMockInitialValues({'uid': 'reconnect-user'});
    await SharedPreferencesUtil.init();
    analytics = _RecordingAnalytics();
    AnalyticsManager.configure(analytics);
    await AnalyticsManager.init();
  });

  tearDown(AnalyticsManager.resetForTesting);

  group('ReconnectNudge.days', () {
    int? days({BtDevice? paired, bool connected = false, int? hoursAgo = 96, DateTime? dismissedAt}) =>
        ReconnectNudge.days(
          paired: paired,
          connected: connected,
          lastConnectedAt: hoursAgo == null ? null : _now.subtract(Duration(hours: hoursAgo)),
          dismissedAt: dismissedAt,
          now: _now,
        );

    test('counts whole days once a paired Omi has been away three days', () {
      expect(days(paired: _omi, hoursAgo: 72), 3);
      expect(days(paired: _omi, hoursAgo: 96), 4);
      expect(days(paired: _omi, hoursAgo: 71), isNull);
    });

    test('stays hidden for no pairing, another brand, a live link or no stamp', () {
      expect(days(), isNull);
      expect(days(paired: BtDevice.empty()), isNull);
      expect(days(paired: BtDevice(id: 'p-1', name: 'Plaud', type: DeviceType.plaud, rssi: -50)), isNull);
      expect(days(paired: _omi, connected: true), isNull);
      expect(days(paired: _omi, hoursAgo: null), isNull);
    });

    test('a close holds for a day, then the row may return', () {
      expect(days(paired: _omi, dismissedAt: _now.subtract(const Duration(hours: 23))), isNull);
      expect(days(paired: _omi, dismissedAt: _now.subtract(const Duration(hours: 24))), 4);
    });
  });

  testWidgets('shows one quiet row for an Omi away four days, logged once', (tester) async {
    await _seed(device: _omi, daysAgo: 4.2);
    final provider = _FakeDeviceProvider();

    await _pump(tester, provider);
    provider.notifyListeners();
    await tester.pump();
    await tester.runAsync(() => AnalyticsManager.flushPending(force: true));

    expect(find.byKey(_row), findsOneWidget);
    expect(find.text("Your Omi hasn't connected in 4 days"), findsOneWidget);
    expect(find.byKey(_reconnect), findsOneWidget);
    expect(analytics.named('Reconnect Nudge').map((e) => e.$1), ['Reconnect Nudge Shown']);
    expect(analytics.events.last.$2, containsPair('days_since_connected', 4));
  });

  testWidgets('never paired, recently connected or a non-Omi device: nothing', (tester) async {
    await _seed();
    await _pump(tester, _FakeDeviceProvider());
    expect(find.byKey(_row), findsNothing);

    await _seed(device: _omi, daysAgo: 2);
    await _pump(tester, _FakeDeviceProvider());
    expect(find.byKey(_row), findsNothing);

    await _seed(device: BtDevice(id: 'p-1', name: 'Plaud', type: DeviceType.plaud, rssi: -50), daysAgo: 9);
    await _pump(tester, _FakeDeviceProvider());
    expect(find.byKey(_row), findsNothing);
  });

  testWidgets('an install from before the row starts its clock instead of nudging at once', (tester) async {
    await _seed(device: _omi);
    await _pump(tester, _FakeDeviceProvider());

    expect(find.byKey(_row), findsNothing);
    expect(DeviceLastConnected.read(), _now);
  });

  testWidgets('disappears the moment the Omi connects on its own', (tester) async {
    await _seed(device: _omi, daysAgo: 5);
    final provider = _FakeDeviceProvider();
    await _pump(tester, provider);
    expect(find.byKey(_row), findsOneWidget);

    provider.connect();
    await tester.pump();

    expect(find.byKey(_row), findsNothing);
  });

  group('time passing while Home stays open', () {
    testWidgets('a close holds 24 hours, then the row returns without leaving Home', (tester) async {
      var clock = _now;
      await _seed(device: _omi, daysAgo: 4);
      await _pump(tester, _FakeDeviceProvider(), clock: () => clock);

      await tester.tap(find.byKey(_close));
      await tester.pump();
      await tester.runAsync(() => AnalyticsManager.flushPending(force: true));
      expect(find.byKey(_row), findsNothing);
      expect(ReconnectNudge.closedAt(), _now);
      final dismissed = analytics.named('Reconnect Nudge Dismissed');
      expect(dismissed, hasLength(1));
      expect(dismissed.single.$2, containsPair('days_since_connected', 4));

      clock = _now.add(const Duration(hours: 23));
      await tester.pump(const Duration(hours: 23));
      expect(find.byKey(_row), findsNothing, reason: '23 hours after closing');

      clock = _now.add(const Duration(hours: 24));
      await tester.pump(const Duration(hours: 1));
      expect(find.text("Your Omi hasn't connected in 5 days"), findsOneWidget, reason: '24 hours after closing');

      clock = _now.add(const Duration(hours: 25));
      await tester.pump(const Duration(hours: 1));
      expect(find.text("Your Omi hasn't connected in 5 days"), findsOneWidget, reason: '25 hours after closing');
    });

    testWidgets('the row appears when the three days run out, no restart needed', (tester) async {
      var clock = _now;
      await _seed(device: _omi, daysAgo: 71 / 24);
      await _pump(tester, _FakeDeviceProvider(), clock: () => clock);
      expect(find.byKey(_row), findsNothing);

      clock = _now.add(const Duration(minutes: 59));
      await tester.pump(const Duration(minutes: 59));
      expect(find.byKey(_row), findsNothing);

      clock = _now.add(const Duration(hours: 1));
      await tester.pump(const Duration(minutes: 1));
      expect(find.text("Your Omi hasn't connected in 3 days"), findsOneWidget);
    });

    testWidgets('coming back from the background looks again, though no timer ran meanwhile', (tester) async {
      var clock = _now;
      await _seed(device: _omi, daysAgo: 4);
      await _pump(tester, _FakeDeviceProvider(), clock: () => clock);
      await tester.tap(find.byKey(_close));
      await tester.pump();
      expect(find.byKey(_row), findsNothing);

      // Suspended for 30 hours: the wall clock moved, the timers did not.
      clock = _now.add(const Duration(hours: 30));
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();

      expect(find.text("Your Omi hasn't connected in 5 days"), findsOneWidget);
    });
  });

  group('Reconnect', () {
    testWidgets('bringing the Omi back hides the row without the guide', (tester) async {
      await _seed(device: _omi, daysAgo: 5);
      final provider = _FakeDeviceProvider(reconnects: true);
      final guideOpens = <BuildContext>[];
      await _pump(tester, provider, guideOpens: guideOpens);

      await tester.tap(find.byKey(_reconnect));
      await tester.pumpAndSettle();
      await tester.runAsync(() => AnalyticsManager.flushPending(force: true));

      expect(provider.connectCalls, 1);
      expect(guideOpens, isEmpty);
      expect(find.byKey(_row), findsNothing);
      final tapped = analytics.named('Reconnect Nudge Tapped');
      expect(tapped, hasLength(1));
      expect(tapped.single.$2, containsPair('days_since_connected', 5));
    });

    testWidgets('finding nothing opens the guide, again on every new attempt; the row stays', (tester) async {
      await _seed(device: _omi, daysAgo: 5);
      final provider = _FakeDeviceProvider();
      final guideOpens = <BuildContext>[];
      await _pump(tester, provider, guideOpens: guideOpens);

      for (var attempt = 1; attempt <= 3; attempt++) {
        await tester.tap(find.byKey(_reconnect));
        await tester.pumpAndSettle();
        expect(provider.connectCalls, attempt);
        expect(guideOpens, hasLength(attempt));
        expect(find.byKey(_row), findsOneWidget);
      }
    });

    testWidgets('an Omi that never answers gets the guide after the 15 second budget', (tester) async {
      await _seed(device: _omi, daysAgo: 5);
      final guideOpens = <BuildContext>[];
      await _pump(tester, _FakeDeviceProvider(slow: true), guideOpens: guideOpens);

      await tester.tap(find.byKey(_reconnect));
      await tester.pump(const Duration(seconds: 14));
      expect(guideOpens, isEmpty);
      await tester.pump(const Duration(seconds: 1));
      expect(guideOpens, hasLength(1));
    });

    testWidgets('a late connection hides the row and opens nothing', (tester) async {
      await _seed(device: _omi, daysAgo: 5);
      final provider = _FakeDeviceProvider(slow: true);
      final guideOpens = <BuildContext>[];
      await _pump(tester, provider, guideOpens: guideOpens);

      await tester.tap(find.byKey(_reconnect));
      await tester.pump(const Duration(seconds: 5));
      provider.finish(connected: true);
      await tester.pumpAndSettle();
      await tester.pump(const Duration(seconds: 15));

      expect(find.byKey(_row), findsNothing);
      expect(guideOpens, isEmpty);
    });

    testWidgets('closing the row while it tries means no guide afterwards', (tester) async {
      await _seed(device: _omi, daysAgo: 5);
      final provider = _FakeDeviceProvider(slow: true);
      final guideOpens = <BuildContext>[];
      await _pump(tester, provider, guideOpens: guideOpens);

      await tester.tap(find.byKey(_reconnect));
      await tester.pump(const Duration(seconds: 2));
      await tester.tap(find.byKey(_close));
      await tester.pump();
      provider.finish();
      await tester.pump(const Duration(seconds: 15));

      expect(find.byKey(_row), findsNothing);
      expect(guideOpens, isEmpty);
    });

    testWidgets('a page opened over Home while it tries means no guide, even past the budget', (tester) async {
      await _seed(device: _omi, daysAgo: 5);
      final guideOpens = <BuildContext>[];
      await _pump(tester, _FakeDeviceProvider(slow: true), guideOpens: guideOpens);

      await tester.tap(find.byKey(_reconnect));
      await tester.pump(const Duration(seconds: 2));
      Navigator.of(tester.element(find.byKey(_row)))
          .push(MaterialPageRoute<void>(builder: (_) => const Scaffold(body: Text('Elsewhere'))));
      await tester.pump(const Duration(seconds: 1));
      await tester.pump(const Duration(seconds: 15));

      expect(find.text('Elsewhere'), findsOneWidget);
      expect(guideOpens, isEmpty);
    });

    testWidgets('switching to another tab while it tries means no guide', (tester) async {
      await _seed(device: _omi, daysAgo: 5);
      final provider = _FakeDeviceProvider(slow: true);
      final guideOpens = <BuildContext>[];
      final homeVisible = ValueNotifier(true);
      addTearDown(homeVisible.dispose);
      await _pump(tester, provider, guideOpens: guideOpens, homeVisible: homeVisible);

      await tester.tap(find.byKey(_reconnect));
      await tester.pump(const Duration(seconds: 2));
      homeVisible.value = false;
      await tester.pump();
      provider.finish();
      await tester.pump(const Duration(seconds: 15));

      expect(guideOpens, isEmpty);
    });
  });

  group('Bluetooth not usable: the app\'s Bluetooth prompt, never a connect or the device guide', () {
    Future<void> tapAndAnswer(WidgetTester tester, {required String prompt, required String answer}) async {
      await tester.tap(find.byKey(_reconnect));
      await tester.pumpAndSettle();
      expect(find.text(prompt), findsOneWidget);
      await tester.tap(find.text(answer).last);
      await tester.pumpAndSettle();
      expect(find.text(prompt), findsNothing);
    }

    testWidgets('off: every tap, before and after the prompt was acknowledged', (tester) async {
      await _seed(device: _omi, daysAgo: 5);
      final readiness =
          BluetoothReadiness(readState: () async => 'off', permissionState: (_) async => null, observeBridge: false);
      final provider = _FakeDeviceProvider();
      final guideOpens = <BuildContext>[];
      await _pump(tester, provider, guideOpens: guideOpens, readiness: readiness);

      for (var tap = 0; tap < 3; tap++) {
        await tapAndAnswer(tester, prompt: 'Enable Bluetooth', answer: 'OK');
      }
      expect(provider.connectCalls, 0);
      expect(guideOpens, isEmpty);
    });

    testWidgets('off, with the launch prompt already acknowledged before the first tap', (tester) async {
      await _seed(device: _omi, daysAgo: 5);
      final readiness =
          BluetoothReadiness(readState: () async => 'off', permissionState: (_) async => null, observeBridge: false);
      expect(await readiness.ensureReady(BluetoothUse.connection), isFalse);
      readiness.dismissGuidance(readiness.guidance!.id);
      final provider = _FakeDeviceProvider();
      final guideOpens = <BuildContext>[];
      await _pump(tester, provider, guideOpens: guideOpens, readiness: readiness);

      await tapAndAnswer(tester, prompt: 'Enable Bluetooth', answer: 'OK');
      expect(provider.connectCalls, 0);
      expect(guideOpens, isEmpty);
    });

    testWidgets('not allowed: the permission prompt on every tap, before and after Not Now', (tester) async {
      await _seed(device: _omi, daysAgo: 5);
      final readiness = BluetoothReadiness(
        readState: () async => 'on',
        permissionState: (_) async => BluetoothAdapterState.unauthorized,
        observeBridge: false,
      );
      final provider = _FakeDeviceProvider();
      final guideOpens = <BuildContext>[];
      await _pump(tester, provider, guideOpens: guideOpens, readiness: readiness);

      for (var tap = 0; tap < 3; tap++) {
        await tapAndAnswer(tester, prompt: 'Permissions Required', answer: 'Not Now');
      }
      expect(provider.connectCalls, 0);
      expect(guideOpens, isEmpty);
    });
  });

  testWidgets('Reconnect sits under the words at every text size, close on their line', (tester) async {
    await _seed(device: _omi, daysAgo: 4);
    // 3.1x is iOS's largest accessibility size.
    for (final scale in [1.0, 2.0, 3.1]) {
      await tester.pumpWidget(const SizedBox());
      await _pump(tester, _FakeDeviceProvider(), textScale: scale);

      expect(tester.takeException(), isNull, reason: 'no overflow at ${scale}x');
      final text = tester.getRect(find.text("Your Omi hasn't connected in 4 days"));
      final button = tester.getRect(find.byKey(_reconnect));
      final close = tester.getRect(find.byKey(_close));
      expect(button.top, greaterThan(text.bottom - 1), reason: 'Reconnect under the words at ${scale}x');
      expect(close.right, greaterThan(text.right), reason: 'close beside the words at ${scale}x');
      expect(close.top, lessThan(text.bottom), reason: 'close on the status line at ${scale}x');
      expect(close.size.width, greaterThanOrEqualTo(44));
      final label = tester
          .renderObject<RenderParagraph>(find.descendant(of: find.byKey(_reconnect), matching: find.text('Reconnect')));
      expect(label.didExceedMaxLines, isFalse, reason: 'Reconnect is not truncated at ${scale}x');
    }
  });
}
