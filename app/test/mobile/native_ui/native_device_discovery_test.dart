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
import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/capture/connect.dart';
import 'package:omi/pages/onboarding/find_device/page.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/services/devices/bluetooth_readiness.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/bluetooth_guidance_listener.dart';
import 'package:omi/backend/schema/device_guide.dart';
import 'package:omi/widgets/apple_watch_setup_bottom_sheet.dart';
import 'package:omi/widgets/connection_guide_sheet.dart';
import 'package:omi/widgets/device_pairing_sheet.dart';
import 'package:omi/widgets/rayban_meta_setup_sheet.dart';
import 'package:omi/widgets/rayban_meta_input_picker_sheet.dart';

import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
final _l10n = lookupAppLocalizations(const Locale('en'));

/// Discovery state set directly by each test; scanning and connecting only record their calls.
class _FakeOnboarding extends OnboardingProvider {
  final taps = <String>[];
  int scans = 0, cancels = 0;

  @override
  Future<void> handleTap({required BtDevice device, required bool isFromOnboarding, VoidCallback? goNext}) async =>
      taps.add(device.id);

  @override
  Future<void> scanDevices({required VoidCallback onShowDialog, VoidCallback? onShowLocationDialog}) async => scans++;

  @override
  void cancelActiveScan() => cancels++;

  void found(List<BtDevice> devices) {
    deviceList = devices;
    foundDevicesMap = {for (final device in devices) device.id: device};
    notifyListeners();
  }
}

class _AudioOnlyRayBan implements RayBanMetaHostAPI {
  @override
  Future<String> getAvailabilityMode() async => 'audio_only';

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _FakeDevices extends ChangeNotifier implements DeviceProvider {
  int initiated = 0;

  @override
  Future<void> initiateConnection(String caller, {bool boundDeviceOnly = false}) async => initiated++;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

BtDevice _device(String id, String name, [DeviceType type = DeviceType.omi]) =>
    BtDevice(name: name, id: id, type: type, rssi: -40);

AppearanceProvider _appearance() => AppearanceProvider(read: () => 'dark', write: (_) async {});

/// The row [id] as the topmost mounted surface dispatches it right now.
NativeRow nativeProjectedRowFor(WidgetTester tester, String id) => tester
    .stateList<State<IosNativeSurface>>(find.byType(IosNativeSurface))
    .expand(IosNativeSurface.debugDispatchRows)
    .lastWhere((row) => row.id == id);

Map _snapshot(WidgetTester tester) => tester.widget<UiKitView>(find.byType(UiKitView)).creationParams as Map;

List<Map> _sections(WidgetTester tester) => (_snapshot(tester)['sections'] as List).cast<Map>();

Map? _section(WidgetTester tester, String id) => _sections(tester).where((section) => section['id'] == id).firstOrNull;

List<Map> _rows(WidgetTester tester) => [
      ...(_snapshot(tester)['toolbar'] as List).cast<Map>(),
      for (final section in _sections(tester)) ...(section['rows'] as List).cast<Map>(),
    ];

Map? _row(WidgetTester tester, String id) => _rows(tester).where((row) => row['id'] == id).firstOrNull;

/// Sends [id] from the current native view as Swift would; answers the decoded reply (null = ok).
Future<Object?> _send(WidgetTester tester, NativeTestHost host, String id) async {
  final view = host.created.lastWhere((id) => !host.disposed.contains(id));
  final reply = await host.sendFromNative(view, MethodCall('action', {'id': id, 'value': null}));
  await NativeTestHost.settle(tester);
  try {
    return const StandardMethodCodec().decodeEnvelope(reply!);
  } on PlatformException catch (error) {
    return error;
  }
}

Future<(_FakeOnboarding, _FakeDevices)> _pumpConnect(WidgetTester tester, _FakeOnboarding provider) async {
  final devices = _FakeDevices();
  provider.setDeviceProvider(devices);
  await tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider<OnboardingProvider>.value(value: provider),
      ChangeNotifierProvider<DeviceProvider>.value(value: devices),
    ],
    child: NativeTestHost.app(Builder(
        builder: (context) => Scaffold(
            body: TextButton(
                onPressed: () =>
                    Navigator.of(context).push(MaterialPageRoute<void>(builder: (_) => const ConnectDevicePage())),
                child: const Text('open connect'))))),
  ));
  await tester.tap(find.text('open connect'));
  await tester.pump();
  await tester.pump(const Duration(seconds: 1));
  await NativeTestHost.settle(tester);
  return (provider, devices);
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  group('Connect page', () {
    testWidgets('scanning with no results shows the loading status, store links and one scan owner', (tester) async {
      NativeTestHost.install();
      final (provider, devices) = await _pumpConnect(tester, _FakeOnboarding());

      expect(find.byType(FindDevicesPage), findsNothing);
      expect(provider.scans, 1, reason: 'Only the offstage lifecycle scans in native mode');
      expect(devices.initiated, 1);
      final snapshot = _snapshot(tester);
      expect(snapshot['title'], _l10n.connect);
      expect(snapshot['loading'], isTrue);
      expect(snapshot['loadingLabel'], _l10n.searchingForDevices);
      expect((snapshot['toolbar'] as List).map((row) => row['id']), ['connect_back', 'connect_settings']);
      expect(_row(tester, 'connect_settings')!['symbol'], 'gearshape');
      expect(_row(tester, 'connect_searching'), isNull, reason: 'The loading row already says it');
      expect(_sections(tester).map((section) => section['id']), ['connect_more']);
      expect(_row(tester, 'connect_get_device')!['symbol'], 'safari');
      expect(_row(tester, 'connect_guide')!['symbol'], 'info.circle');

      tester.state<NavigatorState>(find.byType(Navigator)).pop();
      await tester.pumpAndSettle();
      expect(provider.cancels, 1, reason: 'Leaving the page cancels the scan it started');
    });

    testWidgets('results project names, badges and the connecting state, never device ids', (tester) async {
      NativeTestHost.install();
      final saved = _device('AA:BB:CC:00:00:01', 'Omi');
      final offline = _device('AA:BB:CC:00:00:02', 'Omi');
      final nearby = _device('AA:BB:CC:00:00:03', 'Plaud', DeviceType.plaud);
      final provider = _FakeOnboarding()..savedDeviceList = [saved, offline];
      await _pumpConnect(tester, provider);
      provider
        ..connectingToDeviceId = nearby.id
        ..found([saved, nearby]);
      await NativeTestHost.settle(tester);

      expect(_snapshot(tester)['loading'], isFalse);
      expect(_row(tester, 'connect_searching')!['title'], _l10n.devicesFoundNearby(2));
      final rows = (_section(tester, 'connect_devices')!['rows'] as List).cast<Map>();
      expect(rows.map((row) => row['id']), ['connect_device:0', 'connect_device:1', 'connect_device:2']);
      expect(
          rows.map((row) => row['title']), ['Omi (${saved.getShortId()})', 'Omi (${offline.getShortId()})', 'Plaud']);
      expect(rows.map((row) => row['subtitle']), [_l10n.saved, _l10n.offline, _l10n.deviceConnecting]);
      expect(rows.every((row) => row['enabled'] == true), isTrue);
      expect(_snapshot(tester).toString(), isNot(contains('AA:BB:CC')));

      provider
        ..isClicked = true
        ..notifyListeners();
      await NativeTestHost.settle(tester);
      expect((_section(tester, 'connect_devices')!['rows'] as List).every((row) => row['enabled'] == false), isTrue);
    });

    testWidgets('nothing found shows the help rows without Not Now', (tester) async {
      NativeTestHost.install();
      final provider = _FakeOnboarding();
      await _pumpConnect(tester, provider);
      provider
        ..enableInstructions = true
        ..notifyListeners();
      await NativeTestHost.settle(tester);

      expect(_snapshot(tester)['loading'], isFalse);
      final none = _section(tester, 'connect_none')!;
      expect(none['title'], _l10n.findDeviceNoneTitle);
      expect(none['footer'], _l10n.findDeviceNoneMessage);
      expect((none['rows'] as List).map((row) => row['id']),
          ['connect_scan_again', 'connect_how_to_pair', 'connect_contact_support']);
      expect(_row(tester, 'connect_scan_again')!['symbol'], 'arrow.clockwise');
      expect(_row(tester, 'connect_searching'), isNull);
    });

    testWidgets('Scan Again cancels, hides the help and rescans through the same owner', (tester) async {
      final host = NativeTestHost.install();
      final provider = _FakeOnboarding();
      await _pumpConnect(tester, provider);
      provider
        ..enableInstructions = true
        ..notifyListeners();
      await NativeTestHost.settle(tester);

      expect(await _send(tester, host, 'connect_scan_again'), isNull);
      expect(provider.cancels, 1);
      expect(provider.scans, 2);
      expect(_section(tester, 'connect_none'), isNull);
      expect(_snapshot(tester)['loading'], isTrue);
    });

    testWidgets('the empty state offers Not Now only with includeSkip', (tester) async {
      final provider = _FakeOnboarding()..enableInstructions = true;
      var skipped = 0;
      late List<NativeSection> withSkip, withoutSkip;
      await tester.pumpWidget(NativeTestHost.app(Builder(builder: (context) {
        List<NativeSection> sections(bool includeSkip) => nativeDiscoverySections(context, provider,
            imageUri: (_) => null,
            onTap: (_) async {},
            onScanAgain: () async {},
            onHowToPair: () {},
            onContactSupport: () {},
            onGetDevice: () async {},
            onConnectionGuide: () {},
            includeSkip: includeSkip,
            onNotNow: () => skipped++);
        withSkip = sections(true);
        withoutSkip = sections(false);
        return const SizedBox();
      })));

      List<String> ids(List<NativeSection> sections) =>
          sections.firstWhere((section) => section.id == 'connect_none').rows.map((row) => row.id).toList();
      expect(ids(withoutSkip), isNot(contains('connect_not_now')));
      expect(
          ids(withSkip), ['connect_scan_again', 'connect_how_to_pair', 'connect_not_now', 'connect_contact_support']);
      await withSkip.expand((section) => section.rows).firstWhere((row) => row.id == 'connect_not_now').action!(null);
      expect(skipped, 1);
    });

    testWidgets('the connected state shows success, the name and a low battery', (tester) async {
      NativeTestHost.install();
      final provider = _FakeOnboarding();
      await _pumpConnect(tester, provider);
      provider
        ..isConnected = true
        ..deviceName = 'Omi'
        ..deviceId = 'AA:BB:CC:00:00:09'
        ..batteryPercentage = 20
        ..notifyListeners();
      await NativeTestHost.settle(tester);

      expect(_sections(tester).map((section) => section['id']), ['connect_status']);
      expect(_row(tester, 'connect_paired')!['title'], _l10n.pairingSuccessful);
      expect(_row(tester, 'connect_device_name')!['title'], 'Omi');
      expect(_row(tester, 'connect_battery'),
          allOf(containsPair('title', _l10n.batteryLevelSemantics(20)), containsPair('symbol', 'battery.25')));

      provider
        ..batteryPercentage = 80
        ..notifyListeners();
      await NativeTestHost.settle(tester);
      expect(_row(tester, 'connect_battery')!['symbol'], 'battery.100');
    });

    testWidgets('a device row taps only a device that is still visible', (tester) async {
      final host = NativeTestHost.install();
      final first = _device('id-1', 'Omi One');
      final second = _device('id-2', 'Omi Two');
      final provider = _FakeOnboarding();
      await _pumpConnect(tester, provider);
      provider.found([first, second]);
      await NativeTestHost.settle(tester);

      expect(await _send(tester, host, 'connect_device:1'), isNull);
      expect(provider.taps, ['id-2']);

      // A projection captured before the list changed still names its own device, which left.
      final stale = nativeProjectedRowFor(tester, 'connect_device:1');
      provider.found([first]);
      await stale.action!(null);
      expect(provider.taps, ['id-2']);

      await NativeTestHost.settle(tester);
      expect(await _send(tester, host, 'connect_device:1'), isA<PlatformException>());
      expect(provider.taps, ['id-2']);
    });

    testWidgets('DEVICE_CONNECTED pops the page from the native owner', (tester) async {
      NativeTestHost.install();
      final provider = _FakeOnboarding();
      await _pumpConnect(tester, provider);
      expect(find.byType(ConnectDevicePage), findsOneWidget);

      provider.notifyInfo('DEVICE_CONNECTED');
      await tester.pumpAndSettle();
      expect(find.byType(ConnectDevicePage), findsNothing);
    });

    testWidgets('an empty device id keeps the complete classic page for good', (tester) async {
      NativeTestHost.install();
      expect(nativeDiscoveryIdsValid([_device('a', 'A'), _device('a', 'B')]), isFalse);
      expect(nativeDiscoveryIdsValid([_device('a', 'A'), _device('b', 'B')]), isTrue);

      final provider = _FakeOnboarding();
      await _pumpConnect(tester, provider);
      expect(find.byType(UiKitView), findsOneWidget);

      provider.found([_device('', 'Nameless')]);
      await NativeTestHost.settle(tester);
      expect(find.byType(UiKitView), findsNothing);
      expect(find.byType(FindDevicesPage), findsOneWidget);
      expect(provider.cancels, 1, reason: 'The native owner handed the scan to the classic page');
      expect(provider.scans, 2, reason: 'FindDevicesPage took the scan over');

      provider.found([_device('id-1', 'Omi')]);
      await NativeTestHost.settle(tester);
      expect(find.byType(UiKitView), findsNothing);
      expect(find.byType(FindDevicesPage), findsOneWidget);
    });

    testWidgets('the flag-off build mounts only the classic page', (tester) async {
      final provider = _FakeOnboarding();
      await _pumpConnect(tester, provider);
      expect(find.byType(IosNativeSurface), findsNothing);
      expect(find.byType(FindDevicesPage), findsOneWidget);
      expect(provider.scans, 1);
    });
  });

  testWidgets('the microphone picker refuses a row from before a reload', (tester) async {
    final host = NativeTestHost.install();
    var load = 0;
    final connected = <String>[];
    final loads = [
      [BluetoothHfpInput(uid: 'uid-a', name: 'Glasses A'), BluetoothHfpInput(uid: 'uid-b', name: 'Glasses B')],
      [BluetoothHfpInput(uid: 'uid-c', name: 'Glasses C')],
    ];
    await tester.pumpWidget(NativeTestHost.app(Scaffold(
        body: RayBanMetaInputPickerSheet(
      native: true,
      onConnected: () {},
      inputLoader: () async => loads[load++],
      connector: (device) async => connected.add(device.id),
    ))));
    await NativeTestHost.settle(tester);

    expect((_section(tester, 'rayban_inputs')!['rows'] as List).map((row) => row['title']), ['Glasses A', 'Glasses B']);
    final stale = nativeProjectedRowFor(tester, 'rayban_input:1');

    expect(await _send(tester, host, '_refresh'), isNull);
    expect((_section(tester, 'rayban_inputs')!['rows'] as List).map((row) => row['title']), ['Glasses C']);

    await stale.action!(null);
    expect(connected, isEmpty, reason: 'uid-b left the list; the old row must not connect uid-c');
    expect(await _send(tester, host, 'rayban_input:1'), isA<PlatformException>());
    expect(await _send(tester, host, 'rayban_input:0'), isNull);
    expect(connected.single, contains('uid-c'));
  });

  testWidgets('guide product ids are unique and every asset passes the native allowlist', (tester) async {
    late List<String> ids, assets;
    await tester.pumpWidget(NativeTestHost.app(Builder(builder: (context) {
      final products = ConnectionGuideSheet.products(context);
      ids = products.map((product) => 'guide_product:${product.id}').toList();
      assets = products.map((product) => product.localImagePath!).toList();
      return const SizedBox();
    })));
    expect(ids.toSet().length, ids.length);
    final allowed = RegExp(r'^assets/images/[A-Za-z0-9_/-]+\.(png|jpg|jpeg|webp)$');
    for (final asset in assets) {
      // nativeAssetImageUri's rule: the bundled-image pattern, no '..' and no empty path segment.
      expect(allowed.hasMatch(asset) && !asset.contains('..') && !asset.split('/').contains(''), isTrue, reason: asset);
    }
  });

  group('side sheets', () {
    testWidgets('Ray-Ban setup projects the audio-only step and Continue pops ready', (tester) async {
      final host = NativeTestHost.install();
      bool? result;
      await tester.pumpWidget(NativeTestHost.app(Builder(
          builder: (context) => TextButton(
              onPressed: () async => result = await Navigator.of(context).push<bool>(
                  MaterialPageRoute(builder: (_) => RayBanMetaSetupSheet(native: true, host: _AudioOnlyRayBan()))),
              child: const Text('open setup')))));
      await tester.tap(find.text('open setup'));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
      await NativeTestHost.settle(tester);

      expect(_sections(tester).single['id'], 'rayban_setup_audio_only');
      expect(_row(tester, 'rayban_setup_title')!['title'], _l10n.raybanMetaAudioOnlyTitle);
      expect(_row(tester, 'rayban_setup_close')!['symbol'], 'xmark');
      expect(await _send(tester, host, 'rayban_setup_continue'), isNull);
      await tester.pumpAndSettle();
      expect(result, isTrue);
    });

    testWidgets('the Apple Watch sheet offers to open the Watch app when Omi is not installed', (tester) async {
      NativeTestHost.install();
      const installed = 'dev.flutter.pigeon.omi_pigeon.WatchRecorderHostAPI.isWatchAppInstalled';
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMessageHandler(
          installed, (_) async => const StandardMessageCodec().encodeMessage(<Object?>[false]));
      addTearDown(() => messenger.setMockMessageHandler(installed, null));
      await tester.pumpWidget(
          NativeTestHost.app(const Scaffold(body: AppleWatchSetupBottomSheet(deviceId: 'watch', native: true))));
      await NativeTestHost.settle(tester);

      expect(_snapshot(tester)['loading'], isFalse);
      expect(_row(tester, 'watch_setup_status')!['title'], _l10n.installOmiOnAppleWatch);
      expect(_row(tester, 'watch_setup_primary'),
          allOf(containsPair('title', _l10n.openWatchApp), containsPair('enabled', true)));
      expect(_row(tester, 'watch_setup_cancel')!['title'], _l10n.cancel);
    });

    testWidgets('the pairing sheet keeps Done and Report an issue', (tester) async {
      final host = NativeTestHost.install();
      var dismissed = 0;
      await tester.pumpWidget(NativeTestHost.app(Scaffold(
          body: DevicePairingSheet(
              native: true,
              product:
                  DeviceGuideProduct(id: 'omi', name: 'Omi', pairingTitle: 'Pair Omi', pairingDescription: 'Hold it.'),
              onDismissAll: () => dismissed++))));
      await NativeTestHost.settle(tester);

      expect(_row(tester, 'pairing_title')!['title'], 'Pair Omi');
      expect(_row(tester, 'pairing_description')!['title'], 'Hold it.');
      expect(_row(tester, 'pairing_report')!['title'], _l10n.reportAnIssue);
      expect(await _send(tester, host, 'pairing_done'), isNull);
      expect(dismissed, 1);
    });
  });

  group('Bluetooth guidance', () {
    test('native results map to the listener steps', () {
      expect(bluetoothGuidanceNativeOutcome(const NativeModalResult('open_settings', {})),
          BluetoothGuidanceOutcome.openSettings);
      expect(bluetoothGuidanceNativeOutcome(const NativeModalResult('enable_bluetooth', {})),
          BluetoothGuidanceOutcome.enable);
      for (final reason in ['cancel', 'dismissed', 'invalidated', 'unmounted']) {
        expect(bluetoothGuidanceNativeOutcome(NativeModalResult(null, const {}, reason: reason)),
            BluetoothGuidanceOutcome.dismiss,
            reason: reason);
      }
      expect(bluetoothGuidanceNativeOutcome(const NativeModalResult(null, {}, reason: 'programmatic')),
          BluetoothGuidanceOutcome.resolved);
    });

    Future<List<String>> pumpListener(WidgetTester tester, BluetoothReadiness readiness,
        {required Object? Function(Map arguments) reply, bool isAndroid = false, List<BluetoothUse>? retried}) async {
      NativeTestHost.install();
      final methods = <String>[];
      final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
      messenger.setMockMethodCallHandler(_config, (call) async {
        methods.add(call.method);
        if (call.method != 'present') return null;
        final answer = reply(call.arguments as Map);
        if (answer is PlatformException) throw answer;
        if (answer is Future) return await answer;
        return answer;
      });
      addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
      final navigatorKey = GlobalKey<NavigatorState>();
      await tester.pumpWidget(ChangeNotifierProvider(
        create: (_) => _appearance(),
        child: MaterialApp(
          navigatorKey: navigatorKey,
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          builder: (context, child) => BluetoothGuidanceListener(
            readiness: readiness,
            navigatorKey: navigatorKey,
            isAndroid: isAndroid,
            retryBlockedOperation: (use) async => retried?.add(use),
            child: child!,
          ),
          home: const Scaffold(body: SizedBox()),
        ),
      ));
      return methods;
    }

    testWidgets('Not Now dismisses the guidance', (tester) async {
      final readiness = BluetoothReadiness(readState: () async => 'off', observeBridge: false);
      Map? presented;
      final methods = await pumpListener(tester, readiness, isAndroid: true, reply: (arguments) {
        presented = arguments;
        return {'action': null, 'values': <String, Object?>{}, 'reason': 'cancel'};
      });

      expect(await readiness.ensureReady(BluetoothUse.discovery), isFalse);
      await tester.pumpAndSettle();

      expect(methods, contains('present'));
      expect(presented!['alert'], isTrue);
      expect(presented!['cancelId'], 'not_now');
      final toolbar = ((presented!['snapshot'] as Map)['toolbar'] as List).map((row) => row['id']);
      expect(toolbar, ['not_now', 'enable_bluetooth']);
      expect(find.byType(Dialog), findsNothing);
      expect(readiness.guidance, isNull);
    });

    testWidgets('Enable Bluetooth requests it and retries the blocked operation', (tester) async {
      var state = 'off';
      final readiness = BluetoothReadiness(
          readState: () async => state,
          requestEnable: () async {
            state = 'on';
            return true;
          },
          observeBridge: false);
      final retried = <BluetoothUse>[];
      await pumpListener(tester, readiness,
          isAndroid: true,
          retried: retried,
          reply: (_) => {'action': 'enable_bluetooth', 'values': <String, Object?>{}, 'reason': 'action'});

      expect(await readiness.ensureReady(BluetoothUse.discovery), isFalse);
      await tester.pumpAndSettle();

      expect(readiness.state, BluetoothAdapterState.on);
      expect(retried, [BluetoothUse.discovery]);
    });

    testWidgets('a permission alert offers Open Settings; iOS power guidance offers OK', (tester) async {
      final readiness = BluetoothReadiness(readState: () async => 'off', observeBridge: false);
      final presented = <Map>[];
      await pumpListener(tester, readiness, reply: (arguments) {
        presented.add(arguments);
        return {'action': null, 'values': <String, Object?>{}, 'reason': 'dismissed'};
      });

      expect(await readiness.ensureReady(BluetoothUse.discovery), isFalse);
      await tester.pumpAndSettle();
      expect(presented.single['cancelId'], 'ok');
      expect(((presented.single['snapshot'] as Map)['toolbar'] as List).map((row) => row['title']), [_l10n.ok]);
      expect(readiness.guidance, isNull);
    });

    testWidgets('guidance resolved elsewhere withdraws the alert', (tester) async {
      var state = 'off';
      final readiness = BluetoothReadiness(readState: () async => state, observeBridge: false);
      final reply = Completer<Object?>();
      final methods = await pumpListener(tester, readiness, reply: (_) => reply.future);

      expect(await readiness.ensureReady(BluetoothUse.discovery), isFalse);
      await tester.pump();
      await tester.pump();
      expect(methods, contains('present'));

      state = 'on';
      expect(await readiness.ensureReady(BluetoothUse.discovery), isTrue);
      await tester.pump();
      await tester.pump();
      expect(methods, contains('dismissPresentation'));
      reply.complete({'action': null, 'values': <String, Object?>{}, 'reason': 'programmatic'});
      await tester.pumpAndSettle();
      expect(readiness.guidance, isNull);
      expect(find.byType(Dialog), findsNothing);
    });

    for (final code in ['invalid_native_presentation', 'unexpected_presenter_error']) {
      testWidgets('a refused presentation falls back to the Flutter dialog: $code', (tester) async {
        final readiness = BluetoothReadiness(readState: () async => 'off', observeBridge: false);
        await pumpListener(tester, readiness, reply: (_) => PlatformException(code: code));

        expect(await readiness.ensureReady(BluetoothUse.discovery), isFalse);
        await tester.pumpAndSettle();
        expect(find.text(_l10n.bluetoothNeeded), findsOneWidget);
        await tester.tap(find.text(_l10n.ok));
        await tester.pumpAndSettle();
        expect(readiness.guidance, isNull);
      });
    }
  });
}
