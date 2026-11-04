import 'dart:async';
import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/services/services.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:quick_actions/quick_actions.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/quick_actions_service.dart';
import 'package:omi/utils/enums.dart';

class _Device extends ChangeNotifier implements DeviceProvider {
  bool connected = false;
  @override
  bool get isConnected => connected;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Capture extends ChangeNotifier implements CaptureProvider {
  RecordingState state = RecordingState.stop;
  @override
  RecordingState get recordingState => state;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Recordings implements LocalRecordingsProvider {
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

class _QuickActions extends QuickActions {
  final publications = <List<ShortcutItem>>[];
  Completer<void>? nextCompletion;
  @override
  Future<void> initialize(QuickActionHandler handler) async {}
  @override
  Future<void> setShortcutItems(List<ShortcutItem> items) {
    publications.add(items);
    final completion = nextCompletion;
    nextCompletion = null;
    return completion?.future ?? Future<void>.value();
  }
}

class _OfflineConnectivity extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];
  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _OfflineConnectivity();
    await ServiceManager.init();
  });
  test('device reference binding emits no device-state notifications', () {
    final device = DeviceProvider(chargingConnectionLoader: (_) async => null);
    addTearDown(device.dispose);
    final capture = _Capture();
    addTearDown(capture.dispose);
    var notifications = 0;
    device.addListener(() => notifications++);
    for (var i = 0; i < 4; i++) {
      device.setProviders(capture, _Recordings());
    }
    expect(notifications, 0);
    expect(device.captureProvider, capture);
  });

  testWidgets('shortcuts publish only changed types/labels and republish after reset', (tester) async {
    final device = _Device();
    final capture = _Capture();
    final native = _QuickActions();
    final service = QuickActionsService.forTesting(quickActions: native);
    late BuildContext context;
    Future<void> mount(Locale locale) => tester.pumpWidget(MultiProvider(
          providers: [
            ChangeNotifierProvider<DeviceProvider>.value(value: device),
            ChangeNotifierProvider<CaptureProvider>.value(value: capture),
          ],
          child: MaterialApp(
            locale: locale,
            localizationsDelegates: AppLocalizations.localizationsDelegates,
            supportedLocales: AppLocalizations.supportedLocales,
            home: Builder(builder: (ctx) {
              context = ctx;
              return const SizedBox();
            }),
          ),
        ));
    await mount(const Locale('en'));
    service.initialize(context);
    for (var i = 0; i < 4; i++) {
      service.updateShortcuts(context);
    }
    expect(native.publications, hasLength(1));
    capture.state = RecordingState.pause;
    service.updateShortcuts(context); // Mute is absent while disconnected.
    expect(native.publications, hasLength(1));
    device.connected = true;
    service.updateShortcuts(context);
    expect(native.publications.last.map((s) => s.type), contains('unmute'));
    capture.state = RecordingState.stop;
    service.updateShortcuts(context);
    expect(native.publications.last.map((s) => s.type), contains('mute'));
    expect(native.publications, hasLength(3));
    await mount(const Locale('es'));
    await tester.pumpAndSettle();
    service.updateShortcuts(context);
    expect(native.publications, hasLength(4));
    service.reset();
    service.initialize(context);
    expect(native.publications, hasLength(5));
    device.connected = false;
    final failure = Completer<void>();
    native.nextCompletion = failure;
    service.updateShortcuts(context);
    failure.completeError(StateError('platform failed'));
    await tester.pump();
    expect(tester.takeException(), isStateError);
    service.updateShortcuts(context);
    expect(native.publications, hasLength(7));
    await tester.pumpWidget(const SizedBox());
    device.dispose();
    capture.dispose();
  });

  testWidgets('a failed publication is retried and the dedupe cache restored on success', (tester) async {
    final device = _Device();
    final capture = _Capture();
    final native = _QuickActions();
    final service = QuickActionsService.forTesting(quickActions: native);
    late BuildContext context;
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
      ],
      child: MaterialApp(
        locale: const Locale('en'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(builder: (ctx) {
          context = ctx;
          return const SizedBox();
        }),
      ),
    ));
    service.initialize(context);
    expect(native.publications, hasLength(1));

    // The platform rejects the first changed publication; the failure clears
    // the dedupe cache and schedules the bounded retry.
    final failure = Completer<void>();
    native.nextCompletion = failure;
    device.connected = true;
    service.updateShortcuts(context);
    failure.completeError(StateError('platform failed'));
    await tester.pump();
    expect(tester.takeException(), isStateError);
    expect(native.publications, hasLength(2));

    // The retry must run even though the failed attempt cleared the cache.
    await tester.pump(const Duration(seconds: 5));
    expect(native.publications, hasLength(3), reason: 'the scheduled retry must republish the failed projection');

    // A successful retry restores the dedupe cache: an unchanged later update
    // must not republish.
    service.updateShortcuts(context);
    expect(native.publications, hasLength(3), reason: 'a retried publication must dedupe like a first success');
    await tester.pumpWidget(const SizedBox());
    device.dispose();
    capture.dispose();
  });

  testWidgets('a superseded failed publication does not retry over a newer projection', (tester) async {
    final device = _Device();
    final capture = _Capture();
    final native = _QuickActions();
    final service = QuickActionsService.forTesting(quickActions: native);
    late BuildContext context;
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<DeviceProvider>.value(value: device),
        ChangeNotifierProvider<CaptureProvider>.value(value: capture),
      ],
      child: MaterialApp(
        locale: const Locale('en'),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Builder(builder: (ctx) {
          context = ctx;
          return const SizedBox();
        }),
      ),
    ));
    service.initialize(context);
    expect(native.publications, hasLength(1));

    // Publication A (connected) starts and its platform call stays pending.
    final failureA = Completer<void>();
    native.nextCompletion = failureA;
    device.connected = true;
    service.updateShortcuts(context);
    expect(native.publications, hasLength(2));

    // While A is pending, state changes again and publication B (disconnected)
    // succeeds and takes over the dedupe cache.
    native.nextCompletion = null;
    device.connected = false;
    service.updateShortcuts(context);
    expect(native.publications, hasLength(3));
    expect(native.publications.last.any((s) => s.type == 'connect_device'), isTrue);

    // A's platform call now fails. The failure is superseded: it must not
    // re-arm A's obsolete projection for retry.
    failureA.completeError(StateError('platform failed late'));
    await tester.pump();
    expect(tester.takeException(), isStateError);

    await tester.pump(const Duration(seconds: 5));
    expect(native.publications, hasLength(3),
        reason: 'a superseded failure must not retry its obsolete projection over the published one');

    // The dedupe cache must still hold B's projection, not be rolled back to A.
    service.updateShortcuts(context);
    expect(native.publications, hasLength(3), reason: 'the superseding projection must keep deduping later updates');
    await tester.pumpWidget(const SizedBox());
    device.dispose();
    capture.dispose();
  });
}
