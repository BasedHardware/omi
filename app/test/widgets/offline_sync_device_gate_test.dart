import 'package:connectivity_plus_platform_interface/connectivity_plus_platform_interface.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/gen/pigeon_communicator.g.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/sync_pending_work.dart';
import 'package:omi/pages/settings/device_settings.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/services.dart';
import 'package:omi/services/wals/wal.dart';
import '../support/typed_conversation_screen.dart' show inertPendingWorkStore;

class _TestConnectivityPlatform extends ConnectivityPlatform {
  @override
  Future<List<ConnectivityResult>> checkConnectivity() async => [ConnectivityResult.none];

  @override
  Stream<List<ConnectivityResult>> get onConnectivityChanged => const Stream.empty();
}

class _FakeStorageConnection implements DeviceConnection {
  _FakeStorageConnection({
    this.connected = true,
    this.storageList = const <int>[],
    this.readFailed = false,
    this.advertisesStorage = false,
  });

  bool connected;
  List<int> storageList;
  bool readFailed;
  bool advertisesStorage;

  @override
  bool get lastStorageListReadFailed => readFailed;

  @override
  bool get advertisesStorageCharacteristic => advertisesStorage;

  @override
  Future<bool> isConnected() async => connected;

  @override
  Future<List<int>> getStorageList() async => storageList;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _GateStubDeviceProvider extends ChangeNotifier implements DeviceProvider {
  _GateStubDeviceProvider({
    required this.capability,
    this.connected = false,
    this.paired,
    this.connectedDev,
    this.multiFile = true,
    this.onProbe,
  });

  DeviceStorageCapability capability;
  final bool connected;
  final BtDevice? paired;
  final BtDevice? connectedDev;
  final bool multiFile;
  final Future<DeviceStorageCapability> Function()? onProbe;

  int probeCalls = 0;
  int reconnectCalls = 0;

  @override
  DeviceStorageCapability get storageCapability => capability;

  @override
  bool get isDeviceStorageSupport => capability == DeviceStorageCapability.supported;

  @override
  bool get supportsMultiFileSync => multiFile;

  @override
  bool get isConnected => connected;

  @override
  bool get isSyncStalled => false;

  @override
  bool get hasRememberedDevice => paired?.id.isNotEmpty ?? false;

  @override
  BtDevice? get pairedDevice => paired;

  @override
  BtDevice? get connectedDevice => connectedDev;

  @override
  int get batteryLevel => 80;

  @override
  bool get isCharging => false;

  @override
  bool get havingNewFirmware => false;

  @override
  String get latestStableFirmwareVersion => '';

  @override
  Future<void> getDeviceInfo({bool forceRefresh = false}) async {}

  @override
  Future<void> setisDeviceStorageSupport() async {
    probeCalls++;
    if (onProbe != null) {
      capability = await onProbe!();
      notifyListeners();
    }
  }

  @override
  Future<void> scanAndConnectToDevice() async {
    reconnectCalls++;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _StubSyncProvider extends ChangeNotifier implements SyncProvider {
  _StubSyncProvider(this._wals);

  final List<Wal> _wals;

  @override
  List<Wal> get allWals => _wals;

  @override
  int get missingWalsInSeconds => 0;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Widget _buildTestApp({
  required DeviceProvider deviceProvider,
  required Widget home,
  SyncProvider? syncProvider,
  Locale locale = const Locale('en'),
}) {
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<DeviceProvider>.value(value: deviceProvider),
      if (syncProvider != null) ChangeNotifierProvider<SyncProvider>.value(value: syncProvider),
    ],
    child: MaterialApp(
      locale: locale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: home,
    ),
  );
}

Future<void> _scrollTo(WidgetTester tester, Finder finder) async {
  await tester.scrollUntilVisible(finder, 200, scrollable: find.byType(Scrollable).first);
  await tester.pump();
}

void main() {
  setUpAll(() async {
    TestWidgetsFlutterBinding.ensureInitialized();
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    ConnectivityPlatform.instance = _TestConnectivityPlatform();
    try {
      await ServiceManager.init();
    } catch (_) {}
  });

  setUp(() async {
    final previousStore = PendingWorkStore.instance;
    final store = inertPendingWorkStore();
    PendingWorkStore.instance = store;
    addTearDown(() {
      PendingWorkStore.instance = previousStore;
      store.dispose();
    });
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('DeviceProvider.setisDeviceStorageSupport capability classification', () {
    test('disconnected device resolves to disconnected capability', () async {
      final provider = DeviceProvider(deviceInfoConnectionLoader: (_) async => null);
      addTearDown(provider.dispose);

      await provider.setisDeviceStorageSupport();

      expect(provider.storageCapability, DeviceStorageCapability.disconnected);
      expect(provider.isDeviceStorageSupport, isFalse);
    });

    test('connected CV1 with non-empty storage list resolves to supported', () async {
      final conn = _FakeStorageConnection(storageList: const [512, 0]);
      final provider = DeviceProvider(deviceInfoConnectionLoader: (_) async => conn);
      addTearDown(provider.dispose);
      final cv1 = BtDevice(
        id: 'cv1-id',
        name: 'Omi',
        type: DeviceType.omi,
        rssi: -50,
        modelNumber: 'Omi CV 1',
      );
      provider.connectedDevice = cv1;
      provider.pairedDevice = cv1;

      await provider.setisDeviceStorageSupport();

      expect(provider.storageCapability, DeviceStorageCapability.supported);
      expect(provider.isDeviceStorageSupport, isTrue);
    });

    test('connected CV1 or failed storage read resolves to checking rather than unsupported', () async {
      final conn = _FakeStorageConnection(storageList: const [], readFailed: true);
      final provider = DeviceProvider(deviceInfoConnectionLoader: (_) async => conn);
      addTearDown(provider.dispose);
      final cv1 = BtDevice(
        id: 'cv1-id',
        name: 'Omi',
        type: DeviceType.omi,
        rssi: -50,
        modelNumber: 'Omi CV 1',
      );
      provider.connectedDevice = cv1;
      provider.pairedDevice = cv1;

      await provider.setisDeviceStorageSupport();

      expect(provider.storageCapability, DeviceStorageCapability.checking);
      expect(provider.isDeviceStorageSupport, isFalse);
    });

    test('connected non-storage device with clean empty read resolves to unsupported', () async {
      final conn = _FakeStorageConnection(
        storageList: const [],
        readFailed: false,
        advertisesStorage: false,
      );
      final provider = DeviceProvider(deviceInfoConnectionLoader: (_) async => conn);
      addTearDown(provider.dispose);
      final limitless = BtDevice(
        id: 'limitless-id',
        name: 'Limitless Pendant',
        type: DeviceType.limitless,
        rssi: -55,
        modelNumber: 'Limitless',
      );
      provider.connectedDevice = limitless;
      provider.pairedDevice = limitless;

      await provider.setisDeviceStorageSupport();

      expect(provider.storageCapability, DeviceStorageCapability.unsupported);
      expect(provider.isDeviceStorageSupport, isFalse);
    });
  });

  group('Shared Offline Sync gate UI behavior', () {
    testWidgets('disconnected paired CV1 in DeviceSettings prompts to reconnect without V1/V2 claims (de & en)',
        (tester) async {
      final cv1 = BtDevice(
        id: 'cv1-paired',
        name: 'Omi',
        type: DeviceType.omi,
        rssi: -60,
        modelNumber: 'Omi CV 1',
      );
      final provider = _GateStubDeviceProvider(
        capability: DeviceStorageCapability.disconnected,
        connected: false,
        paired: cv1,
      );
      addTearDown(provider.dispose);

      await tester.pumpWidget(
        _buildTestApp(
          deviceProvider: provider,
          locale: const Locale('de'),
          home: const DeviceSettings(),
        ),
      );
      await tester.pump();

      await _scrollTo(tester, find.text('Offline-Synchronisierung'));
      await tester.tap(find.text('Offline-Synchronisierung'));
      await tester.pumpAndSettle();

      expect(find.text('Gerät nicht verbunden'), findsOneWidget);
      expect(find.text('Erneut verbinden'), findsOneWidget);
      expect(find.textContaining('V1'), findsNothing);
      expect(find.textContaining('V2'), findsNothing);

      await tester.tap(find.text('Erneut verbinden'));
      await tester.pumpAndSettle();

      expect(provider.reconnectCalls, 1);
    });

    testWidgets('disconnected state with no remembered device shows connect guidance', (tester) async {
      final provider = _GateStubDeviceProvider(
        capability: DeviceStorageCapability.disconnected,
        connected: false,
      );
      addTearDown(provider.dispose);

      await tester.pumpWidget(
        _buildTestApp(
          deviceProvider: provider,
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () => openOfflineSyncForDevice(context, provider),
                child: const Text('Open Offline Sync'),
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      await tester.tap(find.text('Open Offline Sync'));
      await tester.pumpAndSettle();

      expect(find.text('Device Not Connected'), findsOneWidget);
      expect(find.textContaining('connect your Omi device'), findsOneWidget);
      expect(find.textContaining('V1'), findsNothing);
      expect(find.textContaining('V2'), findsNothing);
    });

    testWidgets('checking state re-probes once and offers retry when still unresolved', (tester) async {
      var resolveOnNextProbe = false;
      final provider = _GateStubDeviceProvider(
        capability: DeviceStorageCapability.checking,
        connected: true,
        onProbe: () async =>
            resolveOnNextProbe ? DeviceStorageCapability.unsupported : DeviceStorageCapability.checking,
      );
      addTearDown(provider.dispose);

      await tester.pumpWidget(
        _buildTestApp(
          deviceProvider: provider,
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () => openOfflineSyncForDevice(context, provider),
                child: const Text('Open Offline Sync'),
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      await tester.tap(find.text('Open Offline Sync'));
      await tester.pumpAndSettle();

      expect(provider.probeCalls, 1);
      expect(find.text('Check your Omi storage'), findsOneWidget);
      expect(find.text('Try Again'), findsOneWidget);

      resolveOnNextProbe = true;
      await tester.tap(find.text('Try Again'));
      await tester.pumpAndSettle();

      expect(provider.probeCalls, 2);
      expect(find.text('Offline Sync unavailable'), findsOneWidget);
    });

    testWidgets('genuinely unsupported device shows capability explanation without V1/V2 copy in German',
        (tester) async {
      final provider = _GateStubDeviceProvider(
        capability: DeviceStorageCapability.unsupported,
        connected: true,
      );
      addTearDown(provider.dispose);

      await tester.pumpWidget(
        _buildTestApp(
          deviceProvider: provider,
          locale: const Locale('de'),
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () => openOfflineSyncForDevice(context, provider),
                child: const Text('Open Offline Sync'),
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      await tester.tap(find.text('Open Offline Sync'));
      await tester.pumpAndSettle();

      expect(find.text('Offline-Synchronisierung nicht verfügbar'), findsOneWidget);
      expect(
        find.text(
          'Für die Offline-Synchronisierung ist ein verbundenes Omi-Gerät mit SD-Kartenspeicher erforderlich. Ihr aktuelles Gerät unterstützt dies nicht.',
        ),
        findsOneWidget,
      );
      expect(find.textContaining('V1'), findsNothing);
      expect(find.textContaining('V2'), findsNothing);
    });

    testWidgets('openOfflineSyncDetails uses shared device gate when disconnected with pending device work',
        (tester) async {
      final cv1 = BtDevice(
        id: 'cv1-paired',
        name: 'Omi',
        type: DeviceType.omi,
        rssi: -60,
        modelNumber: 'Omi CV 1',
      );
      final deviceProvider = _GateStubDeviceProvider(
        capability: DeviceStorageCapability.disconnected,
        connected: false,
        paired: cv1,
      );
      final syncProvider = _StubSyncProvider([
        Wal(
          timerStart: 1704067200,
          codec: BleAudioCodec.opus,
          seconds: 60,
          status: WalStatus.miss,
          storage: WalStorage.sdcard,
          device: cv1.id,
          fileNum: 1,
        ),
      ]);
      addTearDown(deviceProvider.dispose);
      addTearDown(syncProvider.dispose);

      await tester.pumpWidget(
        _buildTestApp(
          deviceProvider: deviceProvider,
          syncProvider: syncProvider,
          home: Builder(
            builder: (context) => Scaffold(
              body: TextButton(
                onPressed: () => openOfflineSyncDetails(context, syncProvider),
                child: const Text('Details'),
              ),
            ),
          ),
        ),
      );
      await tester.pump();

      await tester.tap(find.text('Details'));
      await tester.pumpAndSettle();

      expect(find.text('Device Not Connected'), findsOneWidget);
      expect(find.text('Reconnect'), findsOneWidget);
      expect(find.text('Offline Sync unavailable'), findsNothing);
    });
  });

  test('all 49 supported locales have V1/V2-free v2Undetected and v2UndetectedMessage strings', () async {
    for (final locale in AppLocalizations.supportedLocales) {
      final l10n = await AppLocalizations.delegate.load(locale);
      expect(
        l10n.v2Undetected.toLowerCase(),
        isNot(anyOf(contains('v1'), contains('v2'))),
        reason: 'v2Undetected for $locale still mentions V1/V2',
      );
      expect(
        l10n.v2UndetectedMessage.toLowerCase(),
        isNot(anyOf(contains('v1'), contains('v2'))),
        reason: 'v2UndetectedMessage for $locale still mentions V1/V2',
      );
    }
  });
}
