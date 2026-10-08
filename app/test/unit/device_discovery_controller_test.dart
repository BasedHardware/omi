import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/find_device/device_discovery_controller.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/services/devices/connectors/apple_watch_connection.dart';
import 'package:omi/services/devices/discovery/rayban_meta_discoverer.dart';
import 'package:omi/services/devices/transports/device_transport.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/apple_watch_setup_bottom_sheet.dart';

import '../mobile/native_ui/native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
final _l10n = lookupAppLocalizations(const Locale('en'));

/// Records the provider calls discovery makes; nothing reaches BLE.
class _FakeOnboarding extends OnboardingProvider {
  final taps = <BtDevice>[];
  int scans = 0, cancels = 0;

  @override
  Future<void> handleTap({required BtDevice device, required bool isFromOnboarding, VoidCallback? goNext}) async =>
      taps.add(device);

  @override
  Future<void> scanDevices({required VoidCallback onShowDialog, VoidCallback? onShowLocationDialog}) async => scans++;

  @override
  void cancelActiveScan() => cancels++;
}

class _FakeWatch implements WatchRecorderHostAPI {
  _FakeWatch({required this.reachable});
  final bool reachable;

  @override
  Future<bool> isWatchReachable() async => reachable;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeRayBan implements RayBanMetaHostAPI {
  _FakeRayBan({this.mode = 'full', this.registration = 'registered', this.camera = 'granted'});
  final String mode, registration, camera;

  @override
  Future<String> getAvailabilityMode() async => mode;

  @override
  Future<String> getRegistrationState() async => registration;

  @override
  Future<String> getCameraPermissionStatus() async => camera;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _InertTransport implements DeviceTransport {
  @override
  Stream<DeviceTransportState> get connectionStateStream => const Stream.empty();

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeWatchConnection extends AppleWatchDeviceConnection {
  _FakeWatchConnection(BtDevice device, {required this.started}) : super(device, _InertTransport());
  final bool started;

  @override
  Future<bool> checkPermissionAndStartRecording() async => started;
}

final _watch = BtDevice(name: 'Apple Watch', id: 'watch-1', type: DeviceType.appleWatch, rssi: 0);
final _glasses = BtDevice(name: 'Ray-Ban Meta', id: 'rayban-1', type: DeviceType.raybanMeta, rssi: 0);
final _plaud = BtDevice(name: 'Plaud', id: 'plaud-1', type: DeviceType.plaud, rssi: 0);

/// Mounts a page whose element owns the controller, inside a route the controller may pop.
Future<DeviceDiscoveryController> _mount(
  WidgetTester tester,
  _FakeOnboarding provider, {
  DeviceDiscoveryHosts hosts = const DeviceDiscoveryHosts(),
  VoidCallback? goNext,
  Future<void> Function()? onRescan,
  bool isFromOnboarding = true,
}) async {
  late DeviceDiscoveryController controller;
  await tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider<OnboardingProvider>.value(value: provider),
      ChangeNotifierProvider(create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {})),
    ],
    child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: const [Locale('en')],
      home: Scaffold(body: Builder(builder: (context) {
        controller = DeviceDiscoveryController(
          context: context,
          isFromOnboarding: isFromOnboarding,
          goNext: goNext ?? () {},
          onRescan: onRescan,
          hosts: hosts,
        );
        return const SizedBox.expand();
      })),
    ),
  ));
  return controller;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  group('Apple Watch', () {
    testWidgets('an unreachable watch opens the setup sheet and connects nothing', (tester) async {
      final provider = _FakeOnboarding()..deviceList = [_watch];
      final sheets = <AppleWatchSetupBottomSheet>[];
      var connections = 0;
      final controller = await _mount(tester, provider,
          hosts: DeviceDiscoveryHosts(
            watch: () => _FakeWatch(reachable: false),
            ensureConnection: (_, {force = false}) async {
              connections++;
              return null;
            },
            showAppleWatchSetup: (_, sheet) async => sheets.add(sheet),
          ));

      await controller.tap(_watch);

      expect(sheets.single.deviceId, 'watch-1');
      expect(connections, 0);
      expect(provider.isConnected, isFalse);
    });

    testWidgets('a reachable watch that starts recording completes onboarding', (tester) async {
      final provider = _FakeOnboarding()..deviceList = [_watch];
      final forced = <bool>[];
      var nextCalls = 0;
      final controller = await _mount(tester, provider,
          goNext: () => nextCalls++,
          hosts: DeviceDiscoveryHosts(
            watch: () => _FakeWatch(reachable: true),
            ensureConnection: (id, {force = false}) async {
              forced.add(force);
              return _FakeWatchConnection(_watch, started: true);
            },
          ));

      await controller.tap(_watch);

      expect(forced, [true, false]);
      expect(provider.deviceId, 'watch-1');
      expect(provider.isConnected, isTrue);
      expect(nextCalls, 1);
    });

    testWidgets('a reachable watch without microphone permission opens the permission page first', (tester) async {
      final provider = _FakeOnboarding()..deviceList = [_watch];
      VoidCallback? granted;
      var nextCalls = 0;
      final controller = await _mount(tester, provider,
          goNext: () => nextCalls++,
          hosts: DeviceDiscoveryHosts(
            watch: () => _FakeWatch(reachable: true),
            ensureConnection: (id, {force = false}) async => _FakeWatchConnection(_watch, started: false),
            showAppleWatchPermission: (_, connection, onGranted) async => granted = onGranted,
          ));

      await controller.tap(_watch);
      expect(granted, isNotNull);
      expect(provider.isConnected, isFalse);
      expect(nextCalls, 0);

      granted!();
      await tester.pump();
      expect(provider.isConnected, isTrue);
      expect(nextCalls, 1);
    });
  });

  group('Ray-Ban Meta', () {
    testWidgets('audio-only mode explains itself first and a cancelled setup connects nothing', (tester) async {
      final provider = _FakeOnboarding()..deviceList = [_glasses];
      var setups = 0;
      final controller = await _mount(tester, provider,
          hosts: DeviceDiscoveryHosts(
            rayBan: () => _FakeRayBan(mode: 'audio_only'),
            showRayBanSetup: (_) async {
              setups++;
              return false;
            },
          ));

      await controller.tap(_glasses);

      expect(setups, 1);
      expect(provider.taps, isEmpty);
    });

    testWidgets('registered glasses with camera access connect without setup', (tester) async {
      final provider = _FakeOnboarding()..deviceList = [_glasses];
      var setups = 0;
      final controller = await _mount(tester, provider,
          hosts: DeviceDiscoveryHosts(
            rayBan: () => _FakeRayBan(),
            showRayBanSetup: (_) async {
              setups++;
              return true;
            },
          ));

      await controller.tap(_glasses);

      expect(setups, 0);
      expect(provider.taps.single.id, 'rayban-1');
    });

    testWidgets('missing camera access runs setup, then connects the glasses', (tester) async {
      final provider = _FakeOnboarding()..deviceList = [_glasses];
      var setups = 0;
      final controller = await _mount(tester, provider,
          hosts: DeviceDiscoveryHosts(
            rayBan: () => _FakeRayBan(camera: 'denied'),
            showRayBanSetup: (_) async {
              setups++;
              return true;
            },
          ));

      await controller.tap(_glasses);

      expect(setups, 1);
      expect(provider.taps.single.id, 'rayban-1');
    });

    testWidgets('the setup placeholder rescans after setup and connects the real glasses', (tester) async {
      final placeholder = BtDevice(
          name: 'Ray-Ban Meta', id: RayBanMetaDiscoverer.setupPlaceholderId, type: DeviceType.raybanMeta, rssi: 0);
      final provider = _FakeOnboarding()..deviceList = [placeholder];
      final timeouts = <int>[];
      final controller = await _mount(tester, provider,
          hosts: DeviceDiscoveryHosts(
            rayBan: () => _FakeRayBan(registration: 'unregistered'),
            showRayBanSetup: (_) async => true,
            discover: ({int timeout = 5}) async {
              timeouts.add(timeout);
              provider.deviceList = [placeholder, _glasses];
            },
          ));

      await controller.tap(placeholder);

      expect(timeouts, [5]);
      expect(provider.taps.single.id, 'rayban-1');
    });
  });

  testWidgets('an offline saved device explains how to wake it and Try Again rescans', (tester) async {
    final provider = _FakeOnboarding()..savedDeviceList = [_plaud];
    var rescans = 0;
    final controller = await _mount(tester, provider, onRescan: () async => rescans++);

    await controller.tap(_plaud);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));

    expect(provider.taps, isEmpty);
    expect(find.text(_l10n.deviceOfflineWakeHint('Plaud')), findsOneWidget);
    await tester.tap(find.text(_l10n.tryAgain));
    await tester.pump();
    expect(rescans, 1);
  });

  testWidgets('a device that left the visible list is not connected from an earlier projection', (tester) async {
    final provider = _FakeOnboarding()..deviceList = [_plaud];
    provider.foundDevicesMap = {_plaud.id: _plaud};
    final controller = await _mount(tester, provider);

    provider
      ..deviceList = []
      ..foundDevicesMap = {};
    await controller.tapVisible('plaud-1');
    expect(provider.taps, isEmpty);

    provider
      ..deviceList = [_plaud]
      ..foundDevicesMap = {_plaud.id: _plaud};
    await controller.tapVisible('plaud-1');
    expect(provider.taps.single.id, 'plaud-1');
  });

  testWidgets('rescan cancels the running scan, hides the help and scans again', (tester) async {
    final provider = _FakeOnboarding()..enableInstructions = true;
    var resets = 0;
    final controller = await _mount(tester, provider);

    await controller.rescan(onReset: () {
      resets++;
      expect(provider.enableInstructions, isFalse);
      expect(provider.scans, 0);
    });

    expect(provider.cancels, 1);
    expect(resets, 1);
    expect(provider.scans, 1);
  });

  group('firmware warning', () {
    const prefKey = 'firmware_warning_acknowledged_DeviceType.plaud';

    testWidgets('the classic card persists the opt-out only when it was ticked', (tester) async {
      final provider = _FakeOnboarding();
      final controller = await _mount(tester, provider);

      unawaited(controller.showFirmwareWarningIfNeeded(_plaud));
      await tester.pumpAndSettle();
      await tester.tap(find.text(_l10n.iUnderstand));
      await tester.pumpAndSettle();
      expect(SharedPreferencesUtil().getBool(prefKey), isFalse);

      unawaited(controller.showFirmwareWarningIfNeeded(_plaud));
      await tester.pumpAndSettle();
      await tester.tap(find.text(_l10n.dontShowAgain));
      await tester.pump();
      await tester.tap(find.text(_l10n.iUnderstand));
      await tester.pumpAndSettle();
      expect(SharedPreferencesUtil().getBool(prefKey), isTrue);
    });

    for (final (name, reply, persisted) in [
      (
        'acknowledge with the opt-out',
        {
          'action': 'acknowledge',
          'values': {'opt_out': true},
          'reason': 'action'
        },
        true
      ),
      (
        'acknowledge without the opt-out',
        {
          'action': 'acknowledge',
          'values': {'opt_out': false},
          'reason': 'action'
        },
        false
      ),
      ('cancel', {'action': null, 'values': <String, Object?>{}, 'reason': 'cancel'}, false),
      ('a swipe', {'action': null, 'values': <String, Object?>{}, 'reason': 'dismissed'}, false),
    ]) {
      testWidgets('the native confirmation persists the opt-out only on acknowledge: $name', (tester) async {
        NativeTestHost.install();
        final presented = <Map>[];
        final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
        messenger.setMockMethodCallHandler(_config, (call) async {
          if (call.method != 'present') return null;
          presented.add(call.arguments as Map);
          return reply;
        });
        addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
        final controller = await _mount(tester, _FakeOnboarding());

        await controller.showFirmwareWarningIfNeeded(_plaud);

        expect(presented.single['dismissible'], isFalse);
        final snapshot = presented.single['snapshot'] as Map;
        expect((snapshot['toolbar'] as List).map((row) => row['title']), [_l10n.iUnderstand],
            reason: 'Acknowledge-only, as the classic card');
        expect(SharedPreferencesUtil().getBool(prefKey), persisted);
      });
    }

    testWidgets('an acknowledged note is not shown again; a critical warning has no opt-out', (tester) async {
      NativeTestHost.install();
      final presented = <Map>[];
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(_config, (call) async {
        if (call.method == 'present') presented.add((call.arguments as Map)['snapshot'] as Map);
        return {'action': null, 'values': <String, Object?>{}, 'reason': 'cancel'};
      });
      addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
      SharedPreferencesUtil().saveBool(prefKey, true);
      final controller = await _mount(tester, _FakeOnboarding());

      await controller.showFirmwareWarningIfNeeded(_plaud);
      expect(presented, isEmpty);

      final bee = BtDevice(
          name: 'Bee', id: 'bee-1', type: DeviceType.bee, rssi: 0, firmwareRevision: '0.7.0', modelNumber: 'Bee');
      expect(bee.isBeeFirmwareUnsupported, isTrue);
      await controller.showFirmwareWarningIfNeeded(bee);
      final rows = [
        for (final section in (presented.single['sections'] as List).cast<Map>()) ...(section['rows'] as List)
      ];
      expect(rows.map((row) => row['kind']), isNot(contains('toggle')));
    });
  });
}
