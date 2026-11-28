import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/l10n/app_localizations_en.dart';
import 'package:omi/pages/onboarding/find_device/pairing_failure_card.dart';
import 'package:omi/providers/onboarding_provider.dart';
import 'package:omi/services/devices/pairing_failure.dart';
import 'package:omi/services/services.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/analytics_adapter.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../integration_test/visual_audit/fakes.dart' show AuditDeviceProvider;
import '../widgets/onboarding_polish_test.dart' as polish;

typedef Reason = DeviceConnectFailureShownFailureReason;

class DiscoveryDeviceProvider extends AuditDeviceProvider {
  DiscoveryDeviceProvider({super.device, super.connected, super.battery});

  bool? chargingNow;
  BtDevice? resolvedDevice;
  int? liveBattery;

  @override
  BtDevice? get capabilityNormalizedDevice => resolvedDevice ?? super.capabilityNormalizedDevice;

  @override
  int get batteryLevel => liveBattery ?? super.batteryLevel;

  @override
  bool get isCharging => chargingNow ?? false;

  @override
  bool? get observedChargingStatus => chargingNow;

  void updateCharging(bool value) {
    chargingNow = value;
    notifyListeners();
  }

  void resolveGlass(BtDevice discovered) {
    resolvedDevice = discovered.copyWith(type: DeviceType.openglass);
    notifyListeners();
  }

  void updateBattery(int level) {
    liveBattery = level;
    notifyListeners();
  }

  @override
  void stopDiscoveryScanning() {}
}

class RecordingAdapter implements AnalyticsAdapter {
  final names = <String>[];
  @override
  bool isInitialized = false;
  @override
  Future<void> init() async => isInitialized = true;
  @override
  void track({required String eventName, Map<String, Object>? properties}) => names.add(eventName);
  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  final binding = TestWidgetsFlutterBinding.ensureInitialized();
  const bluetoothChannel = BasicMessageChannel<Object?>(
    'dev.flutter.pigeon.omi_pigeon.BleHostApi.getBluetoothState',
    BleHostApi.pigeonChannelCodec,
  );
  const connectivity = MethodChannel('dev.fluttercommunity.plus/connectivity');
  const connectivityEvents = MethodChannel('dev.fluttercommunity.plus/connectivity_status');
  late RecordingAdapter adapter;
  late OnboardingProvider provider;

  setUpAll(() async {
    // No internet probes: the production service singleton sees an offline
    // platform, while the device-provider seam below handles discovery inertly.
    binding.defaultBinaryMessenger.setMockMethodCallHandler(connectivity, (_) async => ['none']);
    binding.defaultBinaryMessenger.setMockMethodCallHandler(connectivityEvents, (_) async => null);
    await ServiceManager.init();
  });
  tearDownAll(() {
    binding.defaultBinaryMessenger.setMockMethodCallHandler(connectivity, null);
    binding.defaultBinaryMessenger.setMockMethodCallHandler(connectivityEvents, null);
  });
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    AnalyticsManager.resetForTesting();
    PackageInfo.setMockInitialValues(
        appName: 'Omi Test', packageName: 'com.omi.test', version: '1', buildNumber: '1', buildSignature: '');
    adapter = RecordingAdapter();
    AnalyticsManager.configure(adapter);
    await AnalyticsManager.init();
    binding.defaultBinaryMessenger.setMockDecodedMessageHandler<Object?>(bluetoothChannel, (_) async => ['on']);
    provider = OnboardingProvider()
      ..hasBluetoothPermission = true
      ..deviceProvider = DiscoveryDeviceProvider();
  });
  tearDown(() {
    provider.dispose();
    AnalyticsManager.resetForTesting();
    binding.defaultBinaryMessenger.setMockDecodedMessageHandler<Object?>(bluetoothChannel, null);
  });

  Future<void> pumpConnect(WidgetTester tester, {TargetPlatform platform = TargetPlatform.iOS, Key? boundary}) async {
    tester.view.physicalSize = const Size(1179, 2556);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    final child = polish.host(polish.connect(provider), platform: platform);
    await tester.pumpWidget(boundary == null ? child : RepaintBoundary(key: boundary, child: child));
    // FindDevicesPage's post-frame callback invokes the real scanDevices.
    await tester.pump();
    await tester.pump();
  }

  testWidgets('Omi pairing shows one live status and skips the stale percentage', (tester) async {
    final device = BtDevice(id: 'omi-first-charge', name: 'Omi', type: DeviceType.omi, rssi: -50);
    final live = DiscoveryDeviceProvider(device: device, connected: true, battery: 3);
    addTearDown(live.dispose);
    final render = Platform.environment['FIRST_CHARGE_RENDER'] == '1';
    if (render) await tester.runAsync(polish.loadFonts);
    tester.view.physicalSize = const Size(1179, 2556);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    const boundary = Key('first-charge-render');
    await tester.pumpWidget(RepaintBoundary(
      key: boundary,
      child: polish.host(polish.connect(provider, device: live)),
    ));
    await tester.pump();
    await tester.pump();
    provider
      ..isConnected = true
      ..deviceId = device.id
      ..deviceName = device.name
      ..deviceType = device.type
      ..batteryPercentage = 3
      ..setLoading(false);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 500));
    final l10n = AppLocalizationsEn();
    Future<void> capture(String filename) async {
      if (!render) return;
      await tester.runAsync(() async {
        for (final element in find.byType(Image).evaluate()) {
          await precacheImage((element.widget as Image).image, element);
        }
      });
      await tester.pump();
      await tester.runAsync(() async {
        final target = tester.renderObject<RenderRepaintBoundary>(find.byKey(boundary));
        final image = await target.toImage(pixelRatio: 3);
        final png = await image.toByteData(format: ui.ImageByteFormat.png);
        image.dispose();
        File('../.agent-artifacts/ui-evidence/first-charge-mobile/$filename')
          ..createSync(recursive: true)
          ..writeAsBytesSync(png!.buffer.asUint8List());
      });
    }

    expect(find.text(l10n.connected), findsOneWidget);
    expect(find.text(l10n.deviceReadyToUse), findsNothing);
    live.updateCharging(true);
    await tester.pump();
    expect(find.text(l10n.charging), findsOneWidget);
    expect(find.text(l10n.pairingSuccessful), findsNothing);
    expect(find.text('3%'), findsNothing);
    await capture('001-mobile-ios-pairing-charging.png');
    live.updateCharging(false);
    await tester.pump();
    expect(find.text(l10n.deviceReadyToUse), findsOneWidget);
    expect(find.text(l10n.charging), findsNothing);
    expect(find.text('3%'), findsNothing);
    await capture('002-mobile-ios-pairing-ready.png');
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('OmiGlass advertised as Omi keeps its battery level after pairing', (tester) async {
    final device = BtDevice(id: 'glass-discovery', name: 'OmiGlass', type: DeviceType.omi, rssi: -50);
    final live = DiscoveryDeviceProvider(device: device, connected: true, battery: 72);
    addTearDown(live.dispose);
    await tester.pumpWidget(polish.host(polish.connect(provider, device: live)));
    await tester.pump();
    await tester.pump();
    provider
      ..isConnected = true
      ..deviceId = device.id
      ..deviceName = device.name
      ..deviceType = device.type
      ..batteryPercentage = live.batteryLevel
      ..setLoading(false);
    await tester.pump();
    final l10n = AppLocalizationsEn();
    expect(find.text(l10n.pairingSuccessful), findsOneWidget);
    expect(find.text('72%'), findsOneWidget);
    expect(find.text(l10n.deviceReadyToUse), findsNothing);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('late Glass capability switches pairing to the live battery without changing the discovered type',
      (tester) async {
    final device = BtDevice(id: 'glass-capability', name: 'Omi', type: DeviceType.omi, rssi: -50);
    final live = DiscoveryDeviceProvider(device: device, connected: true);
    addTearDown(live.dispose);
    await tester.pumpWidget(polish.host(polish.connect(provider, device: live)));
    await tester.pump();
    provider
      ..isConnected = true
      ..deviceId = device.id
      ..deviceName = device.name
      ..deviceType = device.type
      ..batteryPercentage = 3
      ..setLoading(false);
    await tester.pump();
    final l10n = AppLocalizationsEn();
    expect(find.text(l10n.connected), findsOneWidget);
    expect(find.text('3%'), findsNothing);

    live.resolveGlass(device);
    await tester.pump();
    expect(find.text(l10n.pairingSuccessful), findsOneWidget);
    expect(find.text('3%'), findsNothing);
    live.updateBattery(72);
    await tester.pump();
    expect(find.text('72%'), findsOneWidget);
    expect(provider.deviceType, DeviceType.omi);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('real empty-scan timer retains No Omi Found and never shows or emits a connection failure',
      (tester) async {
    await pumpConnect(tester);
    expect(provider.enableInstructions, isFalse);
    await tester.pump(const Duration(seconds: deviceScanEmptyAfterSeconds));
    await tester.pump();
    expect(provider.enableInstructions, isTrue);
    expect(provider.pairingFailureReason, isNull);
    final l10n = AppLocalizationsEn();
    expect(find.text(l10n.findDeviceNoneTitle), findsOneWidget);
    expect(find.text(l10n.findDeviceNoneMessage), findsOneWidget);
    expect(find.byKey(const Key('find_devices_contact_support')), findsOneWidget);
    expect(find.byKey(const Key('find_devices_scan_again')), findsOneWidget);
    expect(find.byType(PairingFailureCard), findsNothing);
    await AnalyticsManager.flushPending(force: true);
    expect(adapter.names, contains('Device Scan Empty'));
    expect(adapter.names, isNot(contains('Device Connect Failure Shown')));
    provider.onDevices([BtDevice(id: 'omi-appeared', name: 'Omi Appeared', type: DeviceType.omi, rssi: -50)]);
    await tester.pump();
    expect(find.text(l10n.findDeviceNoneTitle), findsNothing);
    expect(find.text('Omi Appeared'), findsOneWidget);
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('onDevices removes reachability card when a discovered device becomes visible', (tester) async {
    await pumpConnect(tester);
    provider.pairingFailureReason = Reason.notFoundOrDropped;
    provider.notifyListeners();
    await tester.pump();
    await AnalyticsManager.flushPending(force: true);
    expect(find.byType(PairingFailureCard), findsOneWidget);
    expect(adapter.names.where((name) => name == 'Device Connect Failure Shown'), hasLength(1));
    provider.onDevices([BtDevice(id: 'omi-late', name: 'Late Omi', type: DeviceType.omi, rssi: -50)]);
    await tester.pump();
    expect(provider.pairingFailureReason, isNull);
    expect(find.byType(PairingFailureCard), findsNothing);
    expect(find.text('Late Omi'), findsOneWidget);
    await tester.pump(const Duration(seconds: deviceScanEmptyAfterSeconds));
    await AnalyticsManager.flushPending(force: true);
    expect(adapter.names.where((name) => name == 'Device Connect Failure Shown'), hasLength(1));
    await tester.pumpWidget(const SizedBox());
  });

  // #17851: a blocked search returned before the delayed help was armed, so once the blocked card was
  // dismissed the page sat on "Searching for devices" with no scan running and no route to support.
  Future<void> expectDelayedHelpAfterBlockedScan(WidgetTester tester, Reason reason) async {
    await pumpConnect(tester);
    expect(provider.pairingFailureReason, reason);
    expect(find.byType(PairingFailureCard), findsOneWidget);
    await tester.pump(const Duration(seconds: deviceScanEmptyAfterSeconds));
    await tester.pump();
    expect(provider.enableInstructions, isTrue);
    await tester.ensureVisible(find.byKey(const Key('pairing_failure_dismiss')));
    await tester.tap(find.byKey(const Key('pairing_failure_dismiss')));
    await tester.pump();
    final l10n = AppLocalizationsEn();
    expect(find.text(l10n.searchingForDevices), findsNothing);
    expect(find.text(l10n.findDeviceNoneTitle), findsOneWidget);
    expect(find.byKey(const Key('find_devices_scan_again')), findsOneWidget);
    expect(find.byKey(const Key('find_devices_contact_support')), findsOneWidget);
    await AnalyticsManager.flushPending(force: true);
    expect(adapter.names, contains('Device Pairing Blocked'));
    // Discovery never ran, so the funnel must not also count it as an empty scan.
    expect(adapter.names, isNot(contains('Device Scan Empty')));
    await tester.pumpWidget(const SizedBox());
  }

  testWidgets('Bluetooth off still arms the delayed help', (tester) async {
    binding.defaultBinaryMessenger.setMockDecodedMessageHandler<Object?>(bluetoothChannel, (_) async => ['off']);
    await expectDelayedHelpAfterBlockedScan(tester, Reason.bluetoothOff);
  });

  testWidgets('denied Bluetooth permission still arms the delayed help', (tester) async {
    const permissions = MethodChannel('flutter.baseflow.com/permissions/methods');
    binding.defaultBinaryMessenger.setMockMethodCallHandler(permissions, (call) async {
      // 0 is PermissionStatus.denied.
      if (call.method == 'requestPermissions') return {for (final p in call.arguments as List) p as int: 0};
      return 0;
    });
    addTearDown(() => binding.defaultBinaryMessenger.setMockMethodCallHandler(permissions, null));
    provider.hasBluetoothPermission = false;
    await expectDelayedHelpAfterBlockedScan(tester, Reason.bluetoothPermissionDenied);
  });

  group('Bluetooth permission blocked in Settings', () {
    const permissions = MethodChannel('flutter.baseflow.com/permissions/methods');
    // What both the status read and the request answer: 0 denied, 1 granted, 4 permanently denied.
    late int status;
    late List<String> calls;
    int count(String method) => calls.where((call) => call == method).length;
    Future<void> backInApp(WidgetTester tester) async {
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pump();
      await tester.pump();
    }

    setUp(() {
      status = 4;
      calls = [];
      binding.defaultBinaryMessenger.setMockMethodCallHandler(permissions, (call) async {
        calls.add(call.method);
        if (call.method == 'requestPermissions') return {for (final p in call.arguments as List) p as int: status};
        if (call.method == 'openAppSettings') return true;
        return status;
      });
      provider.hasBluetoothPermission = false;
    });
    tearDown(() => binding.defaultBinaryMessenger.setMockMethodCallHandler(permissions, null));

    testWidgets('leads with Open Settings, and coming back allowed searches again without a tap', (tester) async {
      await pumpConnect(tester);
      expect(provider.pairingFailureReason, Reason.bluetoothPermissionDenied);
      expect(provider.pairingBlockNeedsSettings, isTrue);
      final openSettings = find.byKey(const Key('pairing_failure_open_settings'));
      expect(tester.widget<OmiButton>(openSettings).variant, OmiButtonVariant.primary);
      expect(
          tester.widget<OmiButton>(find.byKey(const Key('pairing_failure_retry'))).variant, OmiButtonVariant.secondary);
      await tester.ensureVisible(openSettings);
      await tester.tap(openSettings);
      await tester.pump();
      expect(count('openAppSettings'), 1);
      await AnalyticsManager.flushPending(force: true);
      expect(adapter.names.where((name) => name == 'Device Pairing Settings Opened'), hasLength(1));

      // Allowed in Settings, then back in the app: re-read without a prompt, then search.
      status = 1;
      final requests = count('requestPermissions');
      await backInApp(tester);
      expect(count('requestPermissions'), requests);
      expect(provider.hasBluetoothPermission, isTrue);
      expect(provider.pairingFailureReason, isNull);
      expect(provider.pairingBlockNeedsSettings, isFalse);
      expect(find.byType(PairingFailureCard), findsNothing);
      expect(find.text(AppLocalizationsEn().searchingForDevices), findsOneWidget);
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('coming back still denied keeps the card and never prompts', (tester) async {
      await pumpConnect(tester);
      final requests = count('requestPermissions');
      await AnalyticsManager.flushPending(force: true);
      final blocked = adapter.names.where((name) => name == 'Device Pairing Blocked').length;
      await backInApp(tester);
      expect(count('requestPermissions'), requests);
      expect(count('checkPermissionStatus'), greaterThan(0));
      expect(provider.pairingFailureReason, Reason.bluetoothPermissionDenied);
      expect(find.byKey(const Key('pairing_failure_open_settings')), findsOneWidget);
      await AnalyticsManager.flushPending(force: true);
      expect(adapter.names.where((name) => name == 'Device Pairing Blocked'), hasLength(blocked));
      await tester.pumpWidget(const SizedBox());
    });

    testWidgets('a denial the OS can still ask about again keeps Try Again first', (tester) async {
      status = 0;
      await pumpConnect(tester);
      expect(provider.pairingFailureReason, Reason.bluetoothPermissionDenied);
      expect(provider.pairingBlockNeedsSettings, isFalse);
      expect(find.byKey(const Key('pairing_failure_open_settings')), findsNothing);
      expect(
          tester.widget<OmiButton>(find.byKey(const Key('pairing_failure_retry'))).variant, OmiButtonVariant.primary);
      await tester.pumpWidget(const SizedBox());
    });
  });

  test('advertising saved devices clear reachability, but stale-bond recovery is retained', () async {
    final saved = BtDevice(id: 'saved-omi', name: 'Saved Omi', type: DeviceType.omi, rssi: -50);
    await SharedPreferencesUtil().btDeviceSet(saved);
    provider.pairingFailureReason = Reason.notFoundOrDropped;
    provider.onDevices([]);
    expect(provider.visibleDeviceList, isEmpty);
    expect(provider.pairingFailureReason, Reason.notFoundOrDropped);
    provider.onDevices([saved]);
    expect(provider.visibleDeviceList, isNotEmpty);
    expect(provider.pairingFailureReason, isNull);
    provider.pairingFailureReason = Reason.staleBond;
    provider.onDevices([saved]);
    expect(provider.pairingFailureReason, Reason.staleBond);
  });

  testWidgets('render real empty-scan result on iOS and Android with real fonts', (tester) async {
    if (Platform.environment['ONB_POLISH_RENDER'] != '1') return;
    await tester.runAsync(polish.loadFonts);
    const boundary = Key('provider-empty-render');
    for (final platform in [TargetPlatform.iOS, TargetPlatform.android]) {
      debugDefaultTargetPlatformOverride = platform;
      addTearDown(() => debugDefaultTargetPlatformOverride = null);
      await pumpConnect(tester, platform: platform, boundary: boundary);
      await tester.pump(const Duration(seconds: deviceScanEmptyAfterSeconds));
      await tester.pump();
      final scroll = tester.state<ScrollableState>(find.byType(Scrollable).first);
      scroll.position.jumpTo(scroll.position.maxScrollExtent);
      await tester.pump(const Duration(milliseconds: 500));
      expect(find.text(AppLocalizationsEn().findDeviceNoneTitle).hitTestable(), findsOneWidget);
      expect(find.byKey(const Key('find_devices_contact_support')).hitTestable(), findsOneWidget);
      expect(find.byType(PairingFailureCard), findsNothing);
      expect(tester.takeException(), isNull);
      await tester.runAsync(() async {
        final render = tester.element(find.byKey(boundary)).renderObject! as RenderRepaintBoundary;
        final png = await (await render.toImage(pixelRatio: 3)).toByteData(format: ui.ImageByteFormat.png);
        final tag = platform == TargetPlatform.iOS ? '022-mobile-ios' : '023-mobile-android';
        File('../.agent-artifacts/ui-evidence/onb-polish/$tag-connect-empty-scan.png')
            .writeAsBytesSync(png!.buffer.asUint8List());
      });
      await tester.pumpWidget(const SizedBox());
      provider.enableInstructions = false;
    }
    debugDefaultTargetPlatformOverride = null;
  });
}
