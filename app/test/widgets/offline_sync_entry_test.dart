// Exercises the Offline Sync entry from the actual On the Way row, with
// synthetic inventory and a controlled device-capability result.
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/conversations/on_the_way_page.dart';
import 'package:omi/pages/conversations/sync_pending_work.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/services/pending_work/pending_work_store.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_derived_sync_views.dart';

final _now = DateTime(2026, 11, 22, 12);
final _cv1 = BtDevice(id: 'pendant', name: 'Omi CV1', type: DeviceType.omi, rssi: -40);
const _pendingDetails = Key('on_the_way_stalled_details');
const _phoneDetails = Key('phone_local_offline_sync_details');

class _Device extends ChangeNotifier implements DeviceProvider {
  _Device({this.connected = false, this.capability = OfflineStorageCapability.unverified, this.checkedCapability});

  final bool connected;
  OfflineStorageCapability capability;
  final OfflineStorageCapability? checkedCapability;
  int checks = 0;

  @override
  BtDevice? get connectedDevice => connected ? _cv1 : null;
  @override
  BtDevice? get pairedDevice => _cv1;
  @override
  bool get isConnected => connected;
  @override
  bool get supportsMultiFileSync => true;
  @override
  String get currentFirmwareVersion => '3.0.21';
  @override
  RingStatus? get ringStatus => null;
  @override
  OfflineStorageCapability get offlineStorageCapability => capability;

  @override
  Future<void> refreshOfflineStorageCapability() async {
    checks++;
    capability = checkedCapability ?? capability;
    notifyListeners();
  }

  @override
  Future<void> refreshRingStorageStatus() async {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Sync extends ChangeNotifier with WalDerivedSyncViews implements SyncProvider {
  @override
  final allWals = <Wal>[
    Wal(
      timerStart: _now.subtract(const Duration(minutes: 15)).millisecondsSinceEpoch ~/ 1000,
      codec: BleAudioCodec.opus,
      seconds: 60,
      status: WalStatus.miss,
      storage: WalStorage.sdcard,
      device: _cv1.id,
    ),
    Wal(
      timerStart: _now.subtract(const Duration(days: 40)).millisecondsSinceEpoch ~/ 1000,
      codec: BleAudioCodec.opus,
      seconds: 120,
      status: WalStatus.uploaded,
      storage: WalStorage.disk,
      device: _cv1.id,
    )..uploadedAt = 0,
  ];

  @override
  SyncState get syncState => const SyncState();
  @override
  bool get isRateLimited => false;
  @override
  bool get isSyncing => false;
  @override
  bool get isRingDownloading => false;
  @override
  int get readyRingSeconds => 0;
  @override
  bool get isLoadingWals => false;
  @override
  bool get syncCompleted => false;
  @override
  int get clearableWalsCount => 0;
  @override
  List<Wal> get displaySortedWals => allWals;

  @override
  Future<void> discoverDeviceWals({String? firmwareVersion}) async {}

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _User extends ChangeNotifier implements UserProvider {
  @override
  bool get privateCloudSyncEnabled => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<void> _pumpEntry(WidgetTester tester, _Device device,
    {Locale locale = const Locale('en'), bool phoneLocal = false}) async {
  SharedPreferences.setMockInitialValues({});
  await SharedPreferencesUtil.init();
  final sync = _Sync();
  final user = _User();
  final store = PendingWorkStore();
  addTearDown(device.dispose);
  addTearDown(sync.dispose);
  addTearDown(user.dispose);
  addTearDown(store.dispose);
  await tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider<DeviceProvider>.value(value: device),
      ChangeNotifierProvider<SyncProvider>.value(value: sync),
      ChangeNotifierProvider<UserProvider>.value(value: user),
    ],
    child: MaterialApp(
      locale: locale,
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: phoneLocal
          ? Scaffold(
              body: Builder(
                builder: (context) => TextButton(
                  key: _phoneDetails,
                  onPressed: () => openOfflineSyncDetails(context, sync, multiFileSync: true, phoneLocal: true),
                  child: const SizedBox.square(dimension: 48),
                ),
              ),
            )
          : OnTheWayPage(multiFileSync: true, clock: () => _now, pendingWork: store),
    ),
  ));
  await tester.pumpAndSettle();
}

Future<void> _tap(WidgetTester tester, Key key) async {
  final target = find.byKey(key);
  await tester.ensureVisible(target);
  await tester.tap(target);
  await tester.pumpAndSettle();
}

void main() {
  for (final locale in [const Locale('en'), const Locale('de')]) {
    testWidgets('disconnected CV1 in On the Way gives connect guidance in ${locale.languageCode}', (tester) async {
      final device = _Device();
      final labels = lookupAppLocalizations(locale);
      await _pumpEntry(tester, device, locale: locale);

      await _tap(tester, _pendingDetails);

      expect(find.text(labels.connectDeviceForOfflineSync), findsOneWidget);
      expect(find.text(labels.v2Undetected), findsNothing);
      expect(find.byType(AutoSyncPage), findsNothing);
      expect(device.checks, 0);
    });
  }

  testWidgets('confirmed unsupported hardware gets a German capability alert with no generation claim', (tester) async {
    const locale = Locale('de');
    final labels = lookupAppLocalizations(locale);
    await _pumpEntry(tester, _Device(connected: true, capability: OfflineStorageCapability.unsupported),
        locale: locale);

    await _tap(tester, _pendingDetails);

    expect(find.text(labels.v2Undetected), findsOneWidget);
    expect(find.text(labels.v2UndetectedMessage), findsOneWidget);
    expect('${labels.v2Undetected} ${labels.v2UndetectedMessage}',
        isNot(contains(RegExp(r'\bV[12]\b', caseSensitive: false))));
    expect(find.byType(AutoSyncPage), findsNothing);
  });

  testWidgets('supported wearable opens Offline Sync from On the Way without probing again', (tester) async {
    final device = _Device(connected: true, capability: OfflineStorageCapability.supported);
    await _pumpEntry(tester, device);

    await _tap(tester, _pendingDetails);

    expect(find.byType(AutoSyncPage), findsOneWidget);
    expect(device.checks, 0);
  });

  testWidgets('retrying an unverified capability can open Offline Sync after it resolves', (tester) async {
    final device = _Device(connected: true, checkedCapability: OfflineStorageCapability.supported);
    final labels = lookupAppLocalizations(const Locale('en'));
    await _pumpEntry(tester, device);

    await _tap(tester, _pendingDetails);

    expect(find.text(labels.activityAttentionStorageUnknownTitle), findsOneWidget);
    expect(find.text(labels.v2Undetected), findsNothing);
    expect(find.byType(AutoSyncPage), findsNothing);
    expect(device.checks, 0);

    await tester.tap(find.text(labels.cancel));
    await tester.pumpAndSettle();
    expect(device.checks, 0);
    await _tap(tester, _pendingDetails);
    await tester.tap(find.text(labels.retry));
    await tester.pumpAndSettle();

    expect(device.checks, 1);
    expect(find.byType(AutoSyncPage), findsOneWidget);
  });

  testWidgets('phone-local details open with an unrelated device recording and no connected wearable', (tester) async {
    final device = _Device();
    final labels = lookupAppLocalizations(const Locale('en'));
    await _pumpEntry(tester, device, phoneLocal: true);

    await _tap(tester, _phoneDetails);

    expect(find.byType(AutoSyncPage), findsOneWidget);
    expect(find.text(labels.connectDeviceForOfflineSync), findsNothing);
    expect(device.checks, 0);
  });
}
