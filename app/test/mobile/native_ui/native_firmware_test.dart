import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/firmware_mixin.dart';
import 'package:omi/pages/home/firmware_update.dart';
import 'package:omi/pages/home/firmware_update_dialog.dart';
import 'package:omi/pages/home/omiglass_ota_update.dart';
import 'package:omi/pages/settings/developer_firmware_flash_page.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/services/bridges/ble_bridge.dart';
import 'package:omi/services/devices/connectors/omiglass_connection.dart';
import 'package:omi/services/devices/models.dart';
import 'package:omi/services/services.dart';
import 'package:omi/utils/firmware_update_prompt_coordinator.dart';

import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
final _l10n = lookupAppLocalizations(const Locale('en'));
const _zipUrl = 'https://firmware.example/omi-3.0.1.zip';
const _deviceId = 'AA:BB:CC:DD:EE:01';

BtDevice _omi({String firmware = '2.0.10', String name = 'Omi Device'}) => BtDevice(
    id: _deviceId, name: name, type: DeviceType.omi, rssi: -50, modelNumber: 'Omi', firmwareRevision: firmware);

Map _latest({String version = '3.0.1', List<String> steps = const ['no_usb', 'battery', 'internet']}) => {
      'version': version,
      'min_version': '2.0.0',
      'changelog': ['Faster *sync*', 'Longer battery'],
      'zip_url': _zipUrl,
      'ota_update_steps': steps,
      'is_legacy_secure_dfu': true,
    };

/// The firmware owners these pages read; everything else is unused.
class _Device extends ChangeNotifier implements DeviceProvider {
  _Device({this.batteryLevel = 80, this.prepare});

  @override
  int batteryLevel;
  final Future<void> Function()? prepare;
  int updatesStarted = 0;

  @override
  bool get isCharging => false;
  @override
  Map<String, dynamic> get latestOmiGlassFirmwareDetails => const {};
  @override
  void setOnFirmwareUpdatePage(bool value) {}
  @override
  void resetFirmwareUpdateState() {}
  @override
  void setFirmwareUpdateInProgress(bool inProgress) => updatesStarted++;
  @override
  Future<void> prepareDFU() async => prepare?.call();

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// A Wi-Fi OTA connection whose device reports are driven by the test.
class _Glass implements OmiGlassConnection {
  void Function(OmiGlassOtaStatus status)? report;
  final finished = Completer<bool>();
  String? password;
  int cancels = 0;

  @override
  Future<bool> isOtaSupported() async => true;

  @override
  Future<bool> performOtaUpdate({
    required String ssid,
    required String password,
    required String firmwareUrl,
    void Function(OmiGlassOtaStatus status)? onStatusUpdate,
    void Function()? onConnectionLost,
  }) {
    this.password = password;
    report = onStatusUpdate;
    return finished.future;
  }

  @override
  Future<bool> cancelOtaUpdate() async {
    cancels++;
    return true;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Map _snapshot(NativeTestHost host) =>
    host.calls.where((call) => call.$2.method == 'update').last.$2.arguments as Map<Object?, Object?>;

List<Map> _rows(NativeTestHost host) => [
      for (final section in (_snapshot(host)['sections'] as List).cast<Map>()) ...(section['rows'] as List).cast<Map>(),
    ];

Map? _row(NativeTestHost host, String id) => _rows(host).where((row) => row['id'] == id).firstOrNull;

List<String> _ids(NativeTestHost host) => _rows(host).map((row) => row['id'] as String).toList();

List<Object?> _toolbar(NativeTestHost host) =>
    (_snapshot(host)['toolbar'] as List).cast<Map>().map((row) => row['id']).toList();

/// Sends a native command and answers its decoded reply; a refused command throws.
Future<void> _send(WidgetTester tester, NativeTestHost host, String id, [Object? value]) async {
  final reply = await host.sendFromNative(host.created.last, MethodCall('action', {'id': id, 'value': value}));
  const StandardMethodCodec().decodeEnvelope(reply!);
  await NativeTestHost.settle(tester);
}

bool _canPop(WidgetTester tester) => tester
    .widget<PopScope>(find.ancestor(of: find.byType(Scaffold).first, matching: find.byType(PopScope)).first)
    .canPop;

/// Rebuilds the page after a test sets owner fields directly, as the owner's own setState would.
Future<void> _rebuild(WidgetTester tester, Type page) async {
  tester.element(find.byType(page)).markNeedsBuild();
  await NativeTestHost.settle(tester);
}

/// Answers each 'present' on the config channel with [reply]; records the presented requests.
List<Map> _answerPresentations(FutureOr<Object?> Function(Map request) reply, {VoidCallback? onDismiss}) {
  final presented = <Map>[];
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(_config, (call) async {
    if (call.method == 'dismissPresentation') onDismiss?.call();
    if (call.method != 'present') return null;
    final request = call.arguments as Map;
    presented.add(request);
    final answer = await reply(request);
    if (answer is PlatformException) throw answer;
    return answer;
  });
  addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
  return presented;
}

List<Map> _presentedRows(Map request) => [
      for (final section in ((request['snapshot'] as Map)['sections'] as List).cast<Map>())
        ...(section['rows'] as List).cast<Map>(),
    ];

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({'otaWifiSsid': 'Home WiFi', 'otaWifiPassword': 'saved-secret-pw'});
    await SharedPreferencesUtil.init();
    PackageInfo.setMockInitialValues(
        appName: 'Omi', packageName: 'com.friend.ios', version: '1.0.0', buildNumber: '1', buildSignature: '');
  });

  group('FirmwareUpdate', () {
    Future<NativeTestHost> pump(WidgetTester tester, _Device device,
        {required Future<Map> Function() loader, String firmware = '2.0.10', bool rollback = false}) async {
      final host = NativeTestHost.install();
      await tester.pumpWidget(NativeTestHost.app(ChangeNotifierProvider<DeviceProvider>.value(
          value: device,
          child:
              FirmwareUpdate(device: _omi(firmware: firmware), isRollback: rollback, firmwareDetailsLoader: loader))));
      await NativeTestHost.settle(tester);
      return host;
    }

    testWidgets('projects loading, then the available update without the zip URL or device address', (tester) async {
      final details = Completer<Map>();
      final host = await pump(tester, _Device(), loader: () => details.future);
      expect(find.byType(UiKitView), findsOneWidget);
      expect(_snapshot(host)['loading'], true);
      expect(_snapshot(host)['loadingLabel'], _l10n.checkingFirmwareVersion);
      expect(_rows(host), isEmpty);

      details.complete(_latest());
      await NativeTestHost.settle(tester);
      expect(_snapshot(host)['loading'], false);
      expect(_snapshot(host)['title'], _l10n.firmwareUpdate);
      expect(_toolbar(host), ['fw_back']);
      expect(_ids(host), ['fw_current', 'fw_latest', 'fw_changes', 'fw_start']);
      expect(_row(host, 'fw_current')!['subtitle'], '2.0.10');
      expect(_row(host, 'fw_current')!['destructive'], true);
      expect(_row(host, 'fw_latest')!['subtitle'], '3.0.1');
      expect(_row(host, 'fw_start')!['title'], _l10n.updateNow);
      expect(_row(host, 'fw_start')!['enabled'], true);
      // Server release notes stay literal text.
      final blocks = (_row(host, 'fw_changes')!['blocks'] as List).cast<Map>();
      expect(blocks.map((block) => block['text']), [r'Faster \*sync\*', 'Longer battery']);
      expect(blocks.map((block) => block['prefix']), ['•', '•']);
      final json = jsonEncode(_snapshot(host));
      expect(json, isNot(contains(_zipUrl)));
      expect(json, isNot(contains(_deviceId)));
    });

    testWidgets('an up-to-date device offers the guide and no start', (tester) async {
      final host = await pump(tester, _Device(), loader: () async => _latest(version: '2.0.10'));
      expect(_ids(host), ['fw_up_to_date', 'fw_current', 'fw_changes', 'fw_guide']);
      expect(_row(host, 'fw_up_to_date')!['title'], _l10n.yourDeviceIsUpToDate);
      expect(_row(host, 'fw_current')!['destructive'], false);
    });

    testWidgets('a rollback without a stable build says it is already on stable', (tester) async {
      final host = await pump(tester, _Device(), loader: () async => {}, rollback: true);
      expect(_snapshot(host)['title'], _l10n.stableFirmware);
      expect(_row(host, 'fw_up_to_date')!['title'], _l10n.alreadyOnStableFirmware);
    });

    testWidgets('below the battery minimum the start row is disabled and refuses a forged tap', (tester) async {
      final device = _Device(batteryLevel: 8);
      final host = await pump(tester, device, loader: () async => _latest());
      expect(_row(host, 'fw_battery')!['title'], _l10n.firmwareBatteryTooLow(8));
      expect(_row(host, 'fw_battery')!['symbol'], 'battery.25');
      expect(_row(host, 'fw_start')!['enabled'], false);
      await expectLater(_send(tester, host, 'fw_start'), throwsA(isA<PlatformException>()));
      expect(device.updatesStarted, 0);
    });

    testWidgets('start opens the pre-flight checklist; cancelling starts nothing', (tester) async {
      final device = _Device();
      final host = await pump(tester, device, loader: () async => _latest());
      final presented = _answerPresentations((_) => {'action': null, 'values': {}, 'reason': 'cancel'});
      await _send(tester, host, 'fw_start');
      expect(presented, hasLength(1));
      expect(_presentedRows(presented.single).map((row) => row['id']),
          ['firmware_step_no_usb', 'firmware_step_internet', 'firmware_warning']);
      expect(device.updatesStarted, 0);
    });

    testWidgets('busy, success and failure each project their state; no back while busy', (tester) async {
      final host = await pump(tester, _Device(), loader: () async => _latest());
      final state = tester.state(find.byType(FirmwareUpdate)) as FirmwareMixin;

      state
        ..isDownloading = true
        ..downloadProgress = 42;
      await _rebuild(tester, FirmwareUpdate);
      expect(_toolbar(host), isEmpty);
      expect(_canPop(tester), false);
      expect(_ids(host), ['fw_progress', 'fw_warning']);
      expect(_row(host, 'fw_progress')!['title'], _l10n.downloadingFirmware);
      expect(_row(host, 'fw_progress')!['value'], 42);
      expect(_row(host, 'fw_progress')!['subtitle'], '42%');

      state
        ..isDownloading = false
        ..isInstalling = true
        ..installProgress = 250;
      await _rebuild(tester, FirmwareUpdate);
      expect(_row(host, 'fw_progress')!['title'], _l10n.installingFirmware);
      expect(_row(host, 'fw_progress')!['value'], 100, reason: 'out-of-range progress is clamped');

      state
        ..isInstalling = false
        ..isInstalled = true;
      await _rebuild(tester, FirmwareUpdate);
      expect(_canPop(tester), true);
      expect(_toolbar(host), ['fw_back']);
      expect(_ids(host), ['fw_success', 'fw_done']);
      expect(_row(host, 'fw_success')!['subtitle'], _l10n.restartDeviceToComplete('Omi Device'));

      state
        ..isInstalled = false
        ..updateFailure = FirmwareUpdateFailure.download;
      await _rebuild(tester, FirmwareUpdate);
      expect(_ids(host), ['fw_failed', 'fw_retry', 'fw_support']);
      expect(_row(host, 'fw_failed')!['subtitle'], _l10n.firmwareDownloadFailedMessage);
      state.updateFailure = FirmwareUpdateFailure.install;
      await _rebuild(tester, FirmwareUpdate);
      expect(_row(host, 'fw_failed')!['subtitle'], _l10n.firmwareUpdateFailedMessage);
    });
  });

  group('pre-flight sheet', () {
    Future<void> open(WidgetTester tester, Future<void> Function() onUpdateStart) async {
      await tester.pumpWidget(NativeTestHost.app(Builder(
          builder: (context) => TextButton(
              onPressed: () => showFirmwareUpdateSheet(
                  context: context,
                  steps: const ['no_usb', 'battery', 'internet', 'unknown'],
                  onUpdateStart: onUpdateStart),
              child: const Text('open')))));
      await tester.tap(find.text('open'));
      await NativeTestHost.settle(tester);
    }

    testWidgets('Start runs onUpdateStart once, without the battery or unknown items', (tester) async {
      NativeTestHost.install();
      final presented = _answerPresentations((_) => {'action': 'start', 'values': {}, 'reason': 'action'});
      var started = 0;
      await open(tester, () async => started++);
      expect(started, 1);
      final request = presented.single;
      expect(request['alert'], false);
      expect(
          ((request['snapshot'] as Map)['toolbar'] as List).cast<Map>().map((row) => row['id']), ['cancel', 'start']);
      final rows = _presentedRows(request);
      expect(rows.map((row) => row['symbol']), ['powerplug', 'wifi', 'exclamationmark.triangle']);
      expect(rows.first['title'], _l10n.firmwareDisconnectUsb);
      expect(find.byType(FirmwareUpdateSheet), findsNothing);
    });

    testWidgets('a refused presentation keeps the Flutter sheet', (tester) async {
      NativeTestHost.install();
      _answerPresentations((_) => PlatformException(code: 'invalid_native_presentation'));
      var started = 0;
      await open(tester, () async => started++);
      await tester.pump(const Duration(seconds: 1));
      expect(find.byType(FirmwareUpdateSheet), findsOneWidget);
      expect(started, 0);
    });
  });

  group('update-available prompt', () {
    late FirmwareUpdatePromptCoordinator coordinator;
    late FirmwareUpdatePrompt prompt;

    setUpAll(() async {
      try {
        await ServiceManager.init();
      } catch (_) {
        // Already initialized by another test.
      }
    });

    setUp(() {
      coordinator = FirmwareUpdatePromptCoordinator()..setAvailableVersion('3.0.1');
      prompt = coordinator.beginPresentation()!;
    });

    Future<List<NavigatorState>> present(WidgetTester tester) async {
      final accepted = <NavigatorState>[];
      await tester.pumpWidget(NativeTestHost.app(Builder(
          builder: (context) => TextButton(
              onPressed: () => presentFirmwareUpdatePrompt(context,
                  coordinator: coordinator, prompt: prompt, version: '3.0.1', onAccept: accepted.add),
              child: const Text('open')))));
      await tester.tap(find.text('open'));
      await NativeTestHost.settle(tester);
      return accepted;
    }

    testWidgets('the coordinator retracting it is programmatic: nothing is pushed or deferred', (tester) async {
      NativeTestHost.install();
      final reply = Completer<Object?>();
      var dismissals = 0;
      final presented = _answerPresentations((_) => reply.future, onDismiss: () {
        dismissals++;
        if (!reply.isCompleted) reply.complete({'action': null, 'values': {}, 'reason': 'programmatic'});
      });
      final accepted = await present(tester);
      expect(presented, hasLength(1));
      final request = presented.single;
      expect(request['alert'], true);
      expect(request['dismissible'], false);
      expect(request['cancelId'], 'later');
      expect(_presentedRows(request).single['title'], _l10n.firmwareUpdateAvailableDescription('3.0.1'));

      coordinator.invalidatePresentation();
      await NativeTestHost.settle(tester);
      await tester.pump(const Duration(seconds: 3));
      expect(dismissals, 1, reason: 'the presenter was told to dismiss the alert');
      expect(accepted, isEmpty);
      // Completed and not deferred: the same version can be offered again.
      expect(coordinator.beginPresentation(), isNotNull);
    });

    testWidgets('Later defers this version', (tester) async {
      NativeTestHost.install();
      _answerPresentations((_) => {'action': null, 'values': {}, 'reason': 'cancel'});
      final accepted = await present(tester);
      expect(accepted, isEmpty);
      expect(coordinator.beginPresentation(), isNull);
    });

    testWidgets('Update accepts once and hands over the navigator', (tester) async {
      NativeTestHost.install();
      _answerPresentations((_) => {'action': 'update', 'values': {}, 'reason': 'action'});
      final accepted = await present(tester);
      expect(accepted, hasLength(1));
      expect(coordinator.beginPresentation(), isNotNull, reason: 'the prompt completed');
    });

    testWidgets('flag off keeps the Flutter confirmation', (tester) async {
      final accepted = await present(tester);
      expect(find.text(_l10n.firmwareUpdateAvailable), findsOneWidget);
      await tester.tap(find.text(_l10n.later));
      await tester.pumpAndSettle();
      expect(accepted, isEmpty);
      expect(coordinator.beginPresentation(), isNull);
    });

    test('accepting opens the page for the device type', () {
      final glass = _omi(name: 'OmiGlass');
      final details = {'version': '2.1.0'};
      final ota = firmwareUpdatePageFor(omiGlass: true, device: glass, omiGlassDetails: details);
      expect(ota, isA<OmiGlassOtaUpdate>());
      expect((ota as OmiGlassOtaUpdate).device, glass);
      expect(ota.latestFirmwareDetails, details);
      final dfu = firmwareUpdatePageFor(omiGlass: false, device: _omi(), omiGlassDetails: details);
      expect(dfu, isA<FirmwareUpdate>());
      expect((dfu as FirmwareUpdate).isRollback, false);
    });

    testWidgets('an accepted prompt keeps its page when the device unpairs and the route rebuilds', (tester) async {
      await tester.pumpWidget(const SizedBox());
      final context = tester.element(find.byType(SizedBox));
      final provider = DeviceProvider();
      addTearDown(provider.dispose);
      provider.pairedDevice = _omi(name: 'OmiGlass');
      final navigator = _RecordingNavigator();
      provider.acceptFirmwareUpdatePrompt(navigator);
      final route = navigator.routes.single as MaterialPageRoute;
      expect(route.builder(context), isA<OmiGlassOtaUpdate>());
      // The glass reboots during its Wi-Fi OTA and drops its pairing; a root rebuild re-runs the builder.
      provider.pairedDevice = null;
      expect(route.builder(context), isA<OmiGlassOtaUpdate>());
    });
  });

  group('pairing lost', () {
    setUpAll(() async {
      try {
        await ServiceManager.init();
      } catch (_) {
        // Already initialized by another test.
      }
    });

    testWidgets('shows one native alert at a time', (tester) async {
      NativeTestHost.install();
      final reply = Completer<Object?>();
      var requests = 0;
      final presented = _answerPresentations((_) => ++requests == 1 ? reply.future : {'action': null});
      final provider = DeviceProvider();
      addTearDown(provider.dispose);
      await tester.pumpWidget(ChangeNotifierProvider(
          create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {}),
          child: MaterialApp(
              navigatorKey: globalNavigatorKey,
              localizationsDelegates: AppLocalizations.localizationsDelegates,
              supportedLocales: const [Locale('en')],
              home: const SizedBox())));

      BleBridge.instance.pairingLostCallback!();
      BleBridge.instance.pairingLostCallback!();
      await NativeTestHost.settle(tester);
      expect(presented, hasLength(1));
      final snapshot = presented.single['snapshot'] as Map;
      expect(snapshot['title'], _l10n.bluetooth);
      expect((snapshot['toolbar'] as List).cast<Map>().single['title'], _l10n.gotIt);
      expect(presented.single['dismissible'], false);

      reply.complete({'action': null, 'values': {}, 'reason': 'cancel'});
      await NativeTestHost.settle(tester);
      BleBridge.instance.pairingLostCallback!();
      await NativeTestHost.settle(tester);
      expect(presented, hasLength(2), reason: 'a closed alert no longer suppresses the next one');
    });
  });

  group('OmiGlass OTA', () {
    Future<(NativeTestHost, _Glass)> pump(WidgetTester tester) async {
      final host = NativeTestHost.install();
      final glass = _Glass();
      await tester.pumpWidget(NativeTestHost.app(ChangeNotifierProvider<DeviceProvider>.value(
          value: _Device(),
          child: OmiGlassOtaUpdate(
              device: _omi(firmware: '2.0.0', name: 'OmiGlass'),
              latestFirmwareDetails: const {
                'version': '2.1.0',
                'download_url': _zipUrl,
                'changelog': 'Sharper *photos*\n\n  Faster sync  ',
              },
              connect: (_) async => glass))));
      await NativeTestHost.settle(tester);
      return (host, glass);
    }

    testWidgets('the saved password never crosses unless a typed draft is revealed', (tester) async {
      final (host, _) = await pump(tester);
      expect(_toolbar(host), ['ota_back']);
      expect(_ids(host), [
        'ota_current',
        'ota_latest',
        'ota_changes',
        'ota_ssid',
        'ota_password:0',
        'ota_password_saved',
        'ota_password_clear',
        'ota_keep_nearby',
        'ota_install',
      ]);
      expect((_row(host, 'ota_changes')!['blocks'] as List).cast<Map>().map((block) => block['text']),
          [r'Sharper \*photos\*', 'Faster sync']);
      expect(_row(host, 'ota_ssid')!['value'], 'Home WiFi');
      expect(_row(host, 'ota_ssid')!['maximumLength'], 128);
      final password = _row(host, 'ota_password:0')!;
      expect(password['value'], '');
      expect(password['keyboard'], 'password');
      expect(_row(host, 'ota_password_saved')!['subtitle'], _l10n.saved);
      expect(jsonEncode(_snapshot(host)), isNot(contains('saved-secret-pw')));
      expect(jsonEncode(_snapshot(host)), isNot(contains(_zipUrl)));

      // Nothing can reveal the untouched saved password.
      await expectLater(_send(tester, host, 'ota_password_visibility'), throwsA(isA<PlatformException>()));
      expect(jsonEncode(_snapshot(host)), isNot(contains('saved-secret-pw')));

      await _send(tester, host, 'ota_ssid', 'Office');
      expect(_row(host, 'ota_ssid')!['value'], 'Office');

      await _send(tester, host, 'ota_password:0', 'typed-draft');
      expect(_row(host, 'ota_password:0')!['subtitle'], _l10n.enterWifiPassword);
      expect(_row(host, 'ota_password_saved'), isNull);
      expect(jsonEncode(_snapshot(host)), isNot(contains('typed-draft')));
      await _send(tester, host, 'ota_password_visibility');
      expect(_row(host, 'ota_password_revealed')!['subtitle'], 'typed-draft');
      expect(_row(host, 'ota_password_visibility')!['title'], _l10n.hidePassword);

      await _send(tester, host, 'ota_password_clear');
      expect(_row(host, 'ota_password:1'), isNotNull);
      expect(_row(host, 'ota_password:0'), isNull);
      expect(_ids(host), isNot(contains('ota_password_revealed')));
      expect(_ids(host), isNot(contains('ota_password_clear')));
    });

    testWidgets('install uses the typed values; status codes map to the same copy; no back while updating',
        (tester) async {
      final (host, glass) = await pump(tester);
      await _send(tester, host, 'ota_password:0', 'typed-draft');
      await _send(tester, host, 'ota_install');
      expect(glass.password, 'typed-draft');
      expect(SharedPreferencesUtil().otaWifiPassword, 'typed-draft');
      expect(_toolbar(host), isEmpty);
      expect(_canPop(tester), false);
      expect(_snapshot(host)['loading'], true);
      expect(_row(host, 'ota_status_text')!['title'], _l10n.otaStarting);

      Future<void> report(int code, int progress) async {
        glass.report!(OmiGlassOtaStatus(code, progress));
        await NativeTestHost.settle(tester);
      }

      await report(otaStatusWifiConnecting, 0);
      expect(_row(host, 'ota_status_text')!['title'], _l10n.otaWifiConnecting);
      await report(otaStatusWifiConnected, 0);
      expect(_row(host, 'ota_status_text')!['title'], _l10n.otaWifiConnected);
      await report(otaStatusDownloading, 40);
      expect(_snapshot(host)['loading'], false);
      expect(_row(host, 'ota_progress')!['title'], _l10n.downloadingFirmware);
      expect(_row(host, 'ota_progress')!['value'], 40);
      await report(otaStatusDownloadComplete, 50);
      expect(_row(host, 'ota_progress')!['title'], _l10n.installingFirmware);
      await report(otaStatusInstalling, 60);
      expect(_row(host, 'ota_progress')!['title'], _l10n.installingFirmware);
      expect(_ids(host), ['ota_progress', 'ota_warning', 'ota_cancel']);

      await _send(tester, host, 'ota_cancel');
      expect(glass.cancels, 1);
      expect(_toolbar(host), ['ota_back']);
    });

    testWidgets('device failures show their cause with retry and support', (tester) async {
      for (final (code, copy) in [
        (otaStatusWifiFailed, _l10n.otaWifiFailed),
        (otaStatusDownloadFailed, _l10n.otaDownloadFailed),
        (otaStatusInstallFailed, _l10n.otaInstallFailed),
        (otaStatusError, _l10n.firmwareUpdateFailedMessage),
      ]) {
        final (host, glass) = await pump(tester);
        await _send(tester, host, 'ota_install');
        glass.report!(OmiGlassOtaStatus(code, 10));
        await NativeTestHost.settle(tester);
        expect(_ids(host), ['ota_failed', 'ota_retry', 'ota_support']);
        expect(_row(host, 'ota_failed')!['subtitle'], copy);
        await _send(tester, host, 'ota_retry');
        expect(_ids(host), contains('ota_install'));
        await tester.pumpWidget(const SizedBox());
      }
    });

    testWidgets('success offers Done', (tester) async {
      final (host, glass) = await pump(tester);
      await _send(tester, host, 'ota_install');
      expect(glass.password, 'saved-secret-pw', reason: 'an untouched saved password is still used');
      glass.report!(OmiGlassOtaStatus(otaStatusRebooting, 100));
      await NativeTestHost.settle(tester);
      expect(_ids(host), ['ota_success', 'ota_done']);
      expect(_row(host, 'ota_success')!['subtitle'], _l10n.otaUpdatedMessage('OmiGlass'));
      expect(_toolbar(host), ['ota_back']);
    });
  });

  group('developer flash page', () {
    Future<NativeTestHost> pump(WidgetTester tester, _Device device) async {
      final host = NativeTestHost.install();
      await tester.pumpWidget(NativeTestHost.app(ChangeNotifierProvider<DeviceProvider>.value(
          value: device,
          child: DeveloperFirmwareFlashPage(
              zipFilePath: '/private/var/mobile/tmp/picked/omi-dev.zip', fileName: 'omi-dev.zip', device: _omi()))));
      await NativeTestHost.settle(tester);
      return host;
    }

    testWidgets('ready, flashing and flashed', (tester) async {
      final prepared = Completer<void>();
      final host = await pump(tester, _Device(prepare: () => prepared.future));
      expect(_toolbar(host), ['flash_back']);
      expect(_ids(host), ['flash_file_name', 'flash_warning', 'flash_start']);
      expect(_row(host, 'flash_file_name')!['title'], 'omi-dev.zip');
      expect(_row(host, 'flash_file_name')!['symbol'], 'doc.zipper');
      expect(_row(host, 'flash_start')!['destructive'], true);
      expect(jsonEncode(_snapshot(host)), isNot(contains('/private/var')));
      expect(jsonEncode(_snapshot(host)), isNot(contains(_deviceId)));

      await _send(tester, host, 'flash_start');
      expect(_toolbar(host), isEmpty);
      expect(_canPop(tester), false);
      expect(_ids(host), ['flash_file_name', 'flash_progress']);
      final state = tester.state(find.byType(DeveloperFirmwareFlashPage)) as FirmwareMixin;
      state.installProgress = 37;
      await _rebuild(tester, DeveloperFirmwareFlashPage);
      expect(_row(host, 'flash_progress')!['value'], 37);
      expect(_row(host, 'flash_progress')!['subtitle'], '37%');

      state
        ..isInstalling = false
        ..isInstalled = true;
      await _rebuild(tester, DeveloperFirmwareFlashPage);
      expect(_ids(host), ['flash_file_name', 'flash_success']);
      expect(_toolbar(host), ['flash_back']);
      expect(_canPop(tester), true);
      // Leaving disposes the page; the pending DFU continuation never resumes in this test.
      await tester.pumpWidget(const SizedBox());
      prepared.complete();
      await tester.pump(const Duration(seconds: 3));
    });

    testWidgets('a failed flash shows its error and allows leaving', (tester) async {
      final host = await pump(tester,
          _Device(prepare: () async => throw StateError('device refused /private/var/mobile/tmp/picked/omi-dev.zip')));
      await _send(tester, host, 'flash_start');
      expect(_ids(host), ['flash_file_name', 'flash_progress', 'flash_error']);
      // The developer keeps the diagnostic; the picked file's private path is reduced to its name.
      expect(_row(host, 'flash_error')!['title'], 'Bad state: device refused omi-dev.zip');
      expect(jsonEncode(_snapshot(host)), isNot(contains('/private/var')));
      expect(_toolbar(host), ['flash_back']);
      expect(_canPop(tester), true);
    });
  });
}

class _RecordingNavigator extends NavigatorState {
  final routes = <Route<dynamic>>[];

  @override
  Future<T?> push<T extends Object?>(Route<T> route) {
    routes.add(route);
    return Future<T?>.value();
  }
}
