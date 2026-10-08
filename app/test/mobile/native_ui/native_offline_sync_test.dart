import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:nested/nested.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/models/custom_stt_config.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/conversations/sync_page.dart';
import 'package:omi/pages/conversations/synced_conversations_page.dart';
import 'package:omi/pages/conversations/widgets/offline_sync_storage_sheet.dart';
import 'package:omi/providers/appearance_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/sync_confirmation.dart';

import '../../../integration_test/support/native_host_harness.dart';
import 'native_test_host.dart';

const _config = MethodChannel('com.omi.native_ui/config');
final _l10n = lookupAppLocalizations(const Locale('en'));

/// An inert sync owner with seeded recordings; commands are recorded, never performed.
class _Sync extends ChangeNotifier implements SyncProvider {
  SyncState state = const SyncState();
  List<Wal> wals = [];
  WalStatusFilter filter = WalStatusFilter.pending;
  List<SyncedConversationPointer> pointers = [];
  final calls = <String>[];

  void change(SyncState value) {
    state = value;
    notifyListeners();
  }

  @override
  SyncState get syncState => state;
  @override
  List<Wal> get allWals => wals;
  @override
  bool get isLoadingWals => false;
  @override
  WalStatusFilter get statusFilter => filter;
  @override
  void setStatusFilter(WalStatusFilter value) {
    filter = value;
    calls.add('filter:${value.name}');
    notifyListeners();
  }

  @override
  List<Wal> get pendingWals => wals
      .where((w) => w.status == WalStatus.miss || w.status == WalStatus.uploaded || w.isSyncing)
      .where((w) => w.status != WalStatus.corrupted)
      .toList();
  @override
  List<Wal> get syncedWals => wals.where((w) => w.status == WalStatus.synced).toList();
  @override
  List<Wal> get corruptedWals => wals.where((w) => w.status == WalStatus.corrupted).toList();
  @override
  List<Wal> get filteredByStatusWals => switch (filter) {
        WalStatusFilter.pending => pendingWals,
        WalStatusFilter.synced => syncedWals,
        WalStatusFilter.corrupted => corruptedWals,
      };
  @override
  int get pendingStatusCount => pendingWals.length;
  @override
  int get syncedStatusCount => syncedWals.length;
  @override
  int get corruptedStatusCount => corruptedWals.length;
  @override
  List<Wal> get missingWals => wals.where((w) => w.status == WalStatus.miss).toList();
  @override
  List<Wal> get uploadedWals => wals.where((w) => w.status == WalStatus.uploaded).toList();
  @override
  List<Wal> get pendingDeletableWals => wals.where((w) => !w.isSyncing && w.status == WalStatus.miss).toList();
  @override
  int get clearableWalsCount => syncedWals.length + pendingDeletableWals.length + corruptedWals.length;
  @override
  bool get isSyncing => state.isSyncing;
  @override
  bool get syncCompleted => state.isCompleted;
  @override
  bool get isFetchingConversations => state.isFetchingConversations;
  @override
  String? get syncError => state.errorMessage;
  @override
  Wal? get failedWal => state.failedWal;
  @override
  double? get syncSpeedKBps => state.speedKBps;
  @override
  bool get isSdCardSyncing => false;
  @override
  bool get isRateLimited => false;
  @override
  RateLimitReason? get rateLimitReason => null;
  @override
  List<SyncedConversationPointer> get syncedConversationsPointers => pointers;
  @override
  ({int processed, int total}) get offlineServerProcessingCounts => (processed: 0, total: uploadedWals.length);
  @override
  List<Wal> walsForDisplayFilter(WalDisplayFilter filter) => wals;
  @override
  List<Wal> get displaySortedWals => wals;
  @override
  int get needsAttentionWalsCount => 0;
  @override
  Future<void> discoverDeviceWals({String? firmwareVersion}) async {}
  @override
  Future<void> refreshWals() async {}
  @override
  Future<void> syncWals({WakeTrigger trigger = WakeTrigger.userRetry}) async => calls.add('sync');
  @override
  Future<void> syncWal(Wal wal) async => calls.add('sync ${wal.id}');
  @override
  Future<void> retrySync() async => calls.add('retry');
  @override
  void cancelSync() => calls.add('cancel');
  @override
  Future<void> deleteWal(Wal wal) async => calls.add('delete ${wal.id}');
  @override
  Future<void> deleteAllSyncedWals() async => calls.add('clear synced');
  @override
  Future<void> deleteAllPendingWals() async => calls.add('clear pending');
  @override
  Future<void> deleteAllClearableWals() async => calls.add('clear all');
  @override
  Future<void> applySyncedCopyRetention() async => calls.add('retention');
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// A device owner with no BLE behind it.
class _Device extends ChangeNotifier implements DeviceProvider {
  @override
  String get currentFirmwareVersion => 'Unknown';
  @override
  BtDevice? get connectedDevice => null;
  @override
  Future<void> refreshRingStorageStatus() async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Offline extends ConnectivityProvider {
  @override
  bool get isConnected => false;
}

class _Conversations extends ConversationProvider {
  _Conversations() : super(isSignedIn: () => false);
  final updated = <ServerConversation>[];
  @override
  void updateSyncedConversation(ServerConversation conversation) => updated.add(conversation);
}

Wal _wal(int index, {WalStatus status = WalStatus.miss, WalStorage storage = WalStorage.disk, bool syncing = false}) =>
    Wal(
        timerStart: 1790000000 + index * 3600,
        codec: BleAudioCodec.opus,
        seconds: 30,
        status: status,
        storage: storage,
        device: storage == WalStorage.sdcard ? 'sd' : 'phone')
      ..isSyncing = syncing;

/// Answers each native presentation with [reply] and records the snapshots it was asked to show.
List<Map> _answerPresentations(Map<String, Object?>? Function(Map snapshot) reply) {
  final presented = <Map>[];
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(_config, (call) async {
    if (call.method != 'present') return null;
    final snapshot = (call.arguments as Map)['snapshot'] as Map;
    presented.add(snapshot);
    return reply(snapshot);
  });
  addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
  return presented;
}

Map<String, Object?> _confirm(Map _) => {'action': 'confirm', 'values': <String, Object?>{}};
Map<String, Object?> _cancel(Map _) => {'action': null, 'reason': 'cancel'};

String _message(Map snapshot) => ((snapshot['sections'] as List).single['rows'] as List)
    .cast<Map>()
    .firstWhere((row) => row['id'] == 'message')['title'] as String;

Future<NativeTestHost> _pump(WidgetTester tester, Widget home, _Sync sync,
    {List<SingleChildWidget> providers = const []}) async {
  final host = NativeTestHost.install();
  await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AppearanceProvider(read: () => 'dark', write: (_) async {})),
        ChangeNotifierProvider<SyncProvider>.value(value: sync),
        ChangeNotifierProvider(create: (_) => UserProvider(privateCloudSyncFetcher: () async => false)),
        ChangeNotifierProvider(create: (_) => ConnectivityProvider()),
        ChangeNotifierProvider<DeviceProvider>(create: (_) => _Device()),
        ...providers,
      ],
      child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: const [Locale('en')],
          home: home)));
  await NativeTestHost.settle(tester);
  return host;
}

/// Sends [id] from the newest native view, as Swift's command would.
Future<void> _send(WidgetTester tester, NativeTestHost host, String id, [Object? value]) async {
  await host.sendFromNative(host.created.last, MethodCall('action', {'id': id, 'value': value}));
  await NativeTestHost.settle(tester);
}

List<String> _rowIds(WidgetTester tester) => [
      for (final surface in tester.stateList<State<IosNativeSurface>>(find.byType(IosNativeSurface)))
        ...IosNativeSurface.debugDispatchRows(surface).map((row) => row.id),
    ];

/// A recording's main row: its position, then its recording id.
final _walRowPattern = RegExp(r'^sync_wal:\d+:[^:]+$');

String _walRow(WidgetTester tester, int index) =>
    _rowIds(tester).singleWhere((id) => _walRowPattern.hasMatch(id) && id.startsWith('sync_wal:$index:'));

List<NativeSection> _sections(WidgetTester tester) =>
    tester.widget<IosNativeSurface>(find.byType(IosNativeSurface).last).sections;

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  group('SyncPage', () {
    testWidgets('projects the status in the original phase priority', (tester) async {
      final sync = _Sync()..wals = [_wal(0), _wal(1)];
      addTearDown(sync.dispose);
      final host = await _pump(tester, const SyncPage(), sync);
      expect(find.byType(UiKitView), findsOneWidget, reason: 'The page renders natively');

      expect(nativeProjectedRow(tester, 'sync_status_title').title, _l10n.syncCardReadyCount(2));
      expect(_rowIds(tester), contains('sync_start'));
      expect(_rowIds(tester), isNot(contains('sync_cancel')));

      sync.change(const SyncState(status: SyncStatus.syncing, phase: SyncPhase.downloadingFromDevice));
      await NativeTestHost.settle(tester);
      expect(nativeProjectedRow(tester, 'sync_status_title').title, _l10n.syncCardDownloadingTitle);
      expect(nativeProjectedRow(tester, 'sync_cancel').destructive, true);
      expect(_rowIds(tester), containsAll(['sync_busy']));

      sync.change(const SyncState(status: SyncStatus.syncing, phase: SyncPhase.processingOnServer));
      await NativeTestHost.settle(tester);
      expect(nativeProjectedRow(tester, 'sync_status_title').title, _l10n.syncCardProcessing);
      expect(nativeProjectedRow(tester, 'sync_status_title').subtitle, _l10n.syncProcessingBackgroundHint);
      expect(_rowIds(tester), isNot(contains('sync_cancel')));

      sync.change(const SyncState(status: SyncStatus.syncing, phase: SyncPhase.waitingForInternet));
      await NativeTestHost.settle(tester);
      expect(nativeProjectedRow(tester, 'sync_status_title').title, _l10n.syncCardWaitingInternet);

      // An unattributed error replaces the status, with the original message formatting and Retry.
      sync.change(const SyncState(status: SyncStatus.error, errorMessage: 'Exception: device timeout'));
      await NativeTestHost.settle(tester);
      expect(_rowIds(tester), isNot(contains('sync_status_title')));
      expect(nativeProjectedRow(tester, 'sync_error').title, _l10n.deviceNotResponding);
      await _send(tester, host, 'sync_retry');
      expect(sync.calls, ['retry']);

      sync
        ..wals = []
        ..change(const SyncState());
      await NativeTestHost.settle(tester);
      expect(nativeProjectedRow(tester, 'sync_status_title').title, _l10n.syncCardAllBackedUp);
      expect(nativeProjectedRow(tester, 'sync_empty').title, _l10n.noRecordings);
      expect(sync.calls, ['retry'], reason: 'Projecting status never starts a sync');
    });

    testWidgets('Sync confirms custom STT, then the SD card, then syncs; Cancel confirms first', (tester) async {
      await SharedPreferencesUtil().saveCustomSttConfig(const CustomSttConfig(provider: SttProvider.deepgram));
      final sync = _Sync()..wals = [_wal(0, storage: WalStorage.sdcard)];
      addTearDown(sync.dispose);
      final presented = _answerPresentations(_confirm);
      final host = await _pump(tester, const SyncPage(), sync);

      await _send(tester, host, 'sync_start');
      expect(presented.map((snapshot) => snapshot['title']), [_l10n.syncCustomSttWarningTitle, _l10n.sdCardProcessing]);
      expect(_message(presented.last), _l10n.sdCardProcessingMessage(1));
      expect(sync.calls, ['sync']);

      sync.change(const SyncState(status: SyncStatus.syncing, phase: SyncPhase.uploadingToCloud));
      await NativeTestHost.settle(tester);
      await _send(tester, host, 'sync_cancel');
      expect(presented.last['title'], _l10n.cancelSync);
      expect(sync.calls, ['sync', 'cancel']);
    });

    testWidgets('declining the custom STT confirmation never syncs', (tester) async {
      await SharedPreferencesUtil().saveCustomSttConfig(const CustomSttConfig(provider: SttProvider.deepgram));
      final sync = _Sync()..wals = [_wal(0)];
      addTearDown(sync.dispose);
      final presented = _answerPresentations(_cancel);
      final host = await _pump(tester, const SyncPage(), sync);

      await _send(tester, host, 'sync_start');
      expect(presented, hasLength(1));
      expect(sync.calls, isEmpty);
    });

    testWidgets('the filter switches through the provider and carries the counts', (tester) async {
      final sync = _Sync()
        ..wals = [
          _wal(0),
          _wal(1),
          _wal(2, status: WalStatus.synced),
          _wal(3, status: WalStatus.corrupted),
        ];
      addTearDown(sync.dispose);
      final host = await _pump(tester, const SyncPage(), sync);

      final filter = nativeProjectedRow(tester, 'sync_filter');
      expect(filter.value, 'pending');
      expect(filter.options, {
        'pending': '${_l10n.pending}  2',
        'synced': '${_l10n.synced}  1',
        'corrupted': '${_l10n.failedStatus}  1',
      });
      expect(_rowIds(tester).where((id) => _walRowPattern.hasMatch(id)), hasLength(2));

      await _send(tester, host, 'sync_filter', 'synced');
      expect(sync.calls, ['filter:synced']);
      expect(nativeProjectedRow(tester, 'sync_filter').value, 'synced');
      expect(nativeProjectedRow(tester, _walRow(tester, 0)).subtitle, _l10n.syncStatusConversationCreated);

      await _send(tester, host, 'sync_filter', 'corrupted');
      expect(nativeProjectedRow(tester, _walRow(tester, 0)).subtitle, _l10n.syncStatusFileUnavailable);
      expect(nativeProjectedRow(tester, '${_walRow(tester, 0)}:delete').destructive, true);
    });

    testWidgets('pending recordings from several sources group by source, otherwise by hour', (tester) async {
      final sync = _Sync()..wals = [_wal(0), _wal(1, storage: WalStorage.sdcard)];
      addTearDown(sync.dispose);
      await _pump(tester, const SyncPage(), sync);

      final grouped = _sections(tester).where((section) => section.id.startsWith('sync_source:')).toList();
      expect(grouped.map((section) => section.id), ['sync_source:phone', 'sync_source:sd_card']);
      expect(grouped.first.title, '${_l10n.phone} · 1');
      expect(nativeProjectedRow(tester, _walRow(tester, 1)).title, endsWith(_l10n.sdCard));

      sync
        ..wals = [_wal(0), _wal(1)]
        ..notifyListeners();
      await NativeTestHost.settle(tester);
      expect(_sections(tester).where((section) => section.id.startsWith('sync_source:')), isEmpty);
      expect(_sections(tester).where((section) => section.id.startsWith('sync_hour:')), hasLength(2));
    });

    testWidgets('delete asks with the processing-specific copy, then deletes through the provider', (tester) async {
      final uploaded = _wal(0, status: WalStatus.uploaded);
      final waiting = _wal(1);
      final syncing = _wal(2, syncing: true);
      final sync = _Sync()..wals = [uploaded, waiting, syncing];
      addTearDown(sync.dispose);
      final presented = _answerPresentations(_confirm);
      final host = await _pump(tester, const SyncPage(), sync);

      // The projection lists newest first, so look rows up by their recording.
      String rowOf(Wal wal) => _rowIds(tester).firstWhere((id) =>
          _walRowPattern.hasMatch(id) &&
          nativeProjectedRow(tester, id).subtitle ==
              (wal == uploaded
                  ? _l10n.syncStatusUploaded
                  : wal == syncing
                      ? _l10n.syncStatusBackingUp
                      : _l10n.syncStatusWaiting));

      final uploadedRow = nativeProjectedRow(tester, rowOf(uploaded));
      expect(uploadedRow.swipeTrailing, ['delete']);
      await _send(tester, host, rowOf(uploaded), 'delete');
      expect(presented.last['title'], _l10n.deleteWhileProcessingTitle);
      expect(_message(presented.last), _l10n.deleteWhileProcessingMessage);
      expect(sync.calls, ['delete ${uploaded.id}']);

      await _send(tester, host, rowOf(waiting), 'delete');
      expect(presented.last['title'], _l10n.deleteRecording);
      expect(_message(presented.last), _l10n.thisCannotBeUndone);
      expect(sync.calls.last, 'delete ${waiting.id}');

      final syncingRow = nativeProjectedRow(tester, rowOf(syncing));
      expect(syncingRow.options, isEmpty, reason: 'A recording mid-transfer cannot be deleted');
      expect(syncingRow.swipeTrailing, isEmpty);
    });

    testWidgets('Sync without internet asks for it and never syncs', (tester) async {
      final sync = _Sync()..wals = [_wal(0)];
      addTearDown(sync.dispose);
      final presented = _answerPresentations(_confirm);
      final host = await _pump(tester, const SyncPage(), sync,
          providers: [ChangeNotifierProvider<ConnectivityProvider>(create: (_) => _Offline())]);
      await _send(tester, host, 'sync_start');
      expect(presented, isEmpty);
      expect(sync.calls, isEmpty);
    });

    testWidgets('a transferring recording shows clamped progress; a failed one keeps the status and offers retry',
        (tester) async {
      final moving = _wal(0, syncing: true)
        ..syncStartedAt = DateTime(2026, 10, 4)
        ..storageOffset = 250
        ..storageTotalBytes = 1000
        ..syncSpeedKBps = double.nan
        ..syncEtaSeconds = 30;
      final failed = _wal(1);
      final sync = _Sync()
        ..wals = [moving, failed]
        ..state = SyncState(status: SyncStatus.error, errorMessage: 'upload failed', failedWal: failed);
      addTearDown(sync.dispose);
      final host = await _pump(tester, const SyncPage(), sync);
      expect(find.byType(UiKitView), findsOneWidget, reason: 'Odd transfer numbers never invalidate the snapshot');

      final progressId = _rowIds(tester).singleWhere((id) => id.endsWith(':progress'));
      final progress = nativeProjectedRow(tester, progressId);
      expect(progress.kind, 'progress');
      expect(progress.value, .25);
      expect(progress.title, '25% · ${_l10n.etaLabel('30s')}');
      expect(_rowIds(tester), contains('sync_status_title'), reason: 'An attributed error keeps the status');

      final retry = _rowIds(tester).singleWhere((id) => id.endsWith(':retry'));
      expect(retry, startsWith('sync_wal:'));
      expect(retry, contains(failed.id));
      await _send(tester, host, retry);
      expect(sync.calls, ['sync ${failed.id}']);
    });

    testWidgets('a command for a row that shifted to another recording is refused', (tester) async {
      final first = _wal(0);
      final second = _wal(1);
      final sync = _Sync()..wals = [first, second];
      addTearDown(sync.dispose);
      final presented = _answerPresentations(_confirm);
      final host = await _pump(tester, const SyncPage(), sync);
      final stale = _walRow(tester, 0);

      sync
        ..wals = [stale.endsWith(first.id) ? second : first]
        ..notifyListeners();
      await NativeTestHost.settle(tester);
      expect(_walRow(tester, 0), isNot(stale), reason: 'Position 0 now shows the other recording');
      await _send(tester, host, stale, 'delete');
      expect(presented, isEmpty);
      expect(sync.calls, isEmpty);
    });

    testWidgets('projects 200 recordings and grows the window as its end comes into view', (tester) async {
      final sync = _Sync()
        ..filter = WalStatusFilter.synced
        ..wals = [for (var i = 0; i < 450; i++) _wal(i, status: WalStatus.synced)];
      addTearDown(sync.dispose);
      final host = await _pump(tester, const SyncPage(), sync);

      int walRows() => _rowIds(tester).where((id) => _walRowPattern.hasMatch(id)).length;
      expect(walRows(), 200);
      expect(nativeProjectedRow(tester, 'sync_more').onVisible, isNotNull);

      await _send(tester, host, '_visible:sync_more');
      expect(walRows(), 400);
      await _send(tester, host, '_visible:sync_more');
      expect(walRows(), 450);
      expect(_rowIds(tester), isNot(contains('sync_more')));
      expect(sync.calls, isEmpty, reason: 'Windowing is presentation only');
    });
  });

  group('Manage storage', () {
    late bool retentionChanged;

    Future<(NativeTestHost, _Sync)> openSheet(WidgetTester tester) async {
      retentionChanged = false;
      final sync = _Sync()..wals = [_wal(0), _wal(1, status: WalStatus.synced)];
      addTearDown(sync.dispose);
      final host = await _pump(
          tester,
          Builder(
              builder: (context) => TextButton(
                  onPressed: () {
                    final actions = buildManageStorageActions(context, sync,
                        refreshDeviceStorage: () async => sync.calls.add('refresh'),
                        onRetentionChanged: () => retentionChanged = true);
                    Navigator.of(context).push(MaterialPageRoute<void>(
                        builder: (_) => ManageStorageNativeSheet(actions: actions, fallback: const Text('fallback'))));
                  },
                  child: const Text('open'))),
          sync);
      await tester.tap(find.text('open'));
      await NativeTestHost.settle(tester);
      await tester.pump(const Duration(milliseconds: 400));
      await NativeTestHost.settle(tester);
      return (host, sync);
    }

    for (final (id, title, cleared) in [
      ('storage_clear_synced', () => _l10n.deleteSyncedFiles, 'clear synced'),
      ('storage_clear_pending', () => _l10n.deletePendingFiles, 'clear pending'),
      ('storage_clear_all', () => _l10n.deleteAllFiles, 'clear all'),
    ]) {
      testWidgets('$id pops, confirms, clears and re-reads the device storage', (tester) async {
        final presented = _answerPresentations(_confirm);
        final (host, sync) = await openSheet(tester);
        expect(nativeProjectedRow(tester, 'storage_synced').subtitle, '${_l10n.safelyBackedUp} · 1');
        expect(nativeProjectedRow(tester, 'storage_pending').subtitle, '${_l10n.notYetSynced} · 1');

        await _send(tester, host, id);
        await tester.pump(const Duration(seconds: 1));
        await tester.pump(const Duration(seconds: 1));
        expect(presented.single['title'], title());
        expect(sync.calls, [cleared, 'refresh']);
        expect(find.byType(ManageStorageNativeSheet), findsNothing, reason: 'The sheet closes first');
      });
    }

    testWidgets('a declined clear leaves the recordings and storage alone', (tester) async {
      _answerPresentations(_cancel);
      final (host, sync) = await openSheet(tester);
      await _send(tester, host, 'storage_clear_all');
      expect(sync.calls, isEmpty);
    });

    testWidgets('clear is disabled for an empty category and counts follow the provider', (tester) async {
      final (_, sync) = await openSheet(tester);
      sync
        ..wals = [_wal(0)]
        ..notifyListeners();
      await NativeTestHost.settle(tester);
      expect(nativeProjectedRow(tester, 'storage_synced').subtitle, '${_l10n.safelyBackedUp} · 0');
      expect(nativeProjectedRow(tester, 'storage_clear_synced').projection['enabled'], false);
      expect(nativeProjectedRow(tester, 'storage_clear_pending').projection['enabled'], true);
    });

    testWidgets('the auto-remove switch persists and applies the retention when enabled', (tester) async {
      SharedPreferencesUtil().autoRemoveSyncedCopies = false;
      final (host, sync) = await openSheet(tester);
      expect(nativeProjectedRow(tester, 'storage_auto_remove').value, false);

      await _send(tester, host, 'storage_auto_remove', true);
      expect(SharedPreferencesUtil().autoRemoveSyncedCopies, true);
      expect(sync.calls, ['retention']);
      expect(retentionChanged, true);
      expect(nativeProjectedRow(tester, 'storage_auto_remove').value, true);

      await _send(tester, host, 'storage_auto_remove', false);
      expect(SharedPreferencesUtil().autoRemoveSyncedCopies, false);
      expect(sync.calls, ['retention'], reason: 'Turning it off removes nothing');
    });

    testWidgets('the legacy storage sheet runs its own clear callbacks natively', (tester) async {
      final cleared = <String>[];
      final sync = _Sync();
      addTearDown(sync.dispose);
      final host = await _pump(
          tester,
          OfflineSyncStorageSheet(
            nativeTitle: _l10n.manageStorage,
            syncedCount: 0,
            pendingCount: 3,
            totalCount: 3,
            onClearSynced: () => cleared.add('synced'),
            onClearPending: () => cleared.add('pending'),
            onClearAll: () => cleared.add('all'),
          ),
          sync);
      expect(find.byType(UiKitView), findsOneWidget);
      expect(nativeProjectedRow(tester, 'storage_clear_synced').projection['enabled'], false);
      expect(nativeProjectedRow(tester, 'storage_pending').subtitle, '${_l10n.notYetSynced} · 3');
      await _send(tester, host, 'storage_clear_pending');
      await _send(tester, host, 'storage_clear_all');
      expect(cleared, ['pending', 'all']);
    });
  });

  group('Sync confirmations', () {
    Future<BuildContext> mount(WidgetTester tester) async {
      NativeTestHost.install();
      late BuildContext context;
      await tester.pumpWidget(NativeTestHost.app(Builder(builder: (c) {
        context = c;
        return const SizedBox();
      })));
      return context;
    }

    testWidgets('custom STT returns the native choice and skips the prompt otherwise', (tester) async {
      final context = await mount(tester);
      var reply = _confirm;
      final presented = _answerPresentations((snapshot) => reply(snapshot));

      expect(await confirmSyncForCustomStt(context), true);
      expect(presented, isEmpty, reason: 'Omi transcription needs no confirmation');

      await SharedPreferencesUtil().saveCustomSttConfig(const CustomSttConfig(provider: SttProvider.deepgram));
      expect(await confirmSyncForCustomStt(context), true);
      expect(presented.single['title'], _l10n.syncCustomSttWarningTitle);
      expect(_message(presented.single), _l10n.syncCustomSttWarningMessage);
      reply = _cancel;
      expect(await confirmSyncForCustomStt(context), false);
    });

    testWidgets('SD card processing returns the native choice', (tester) async {
      final context = await mount(tester);
      var reply = _confirm;
      final presented = _answerPresentations((snapshot) => reply(snapshot));
      expect(await confirmSdCardProcessing(context, 4), true);
      expect(presented.single['title'], _l10n.sdCardProcessing);
      expect((presented.single['toolbar'] as List).cast<Map>().last['title'], _l10n.process);
      reply = _cancel;
      expect(await confirmSdCardProcessing(context, 4), false);
    });
  });

  group('SyncedConversationsPage', () {
    ServerConversation conversation(String id, String title, {bool locked = false}) => ServerConversation(
        id: id,
        createdAt: DateTime(2026, 10, 4, 9),
        structured: Structured(title, 'Overview'),
        status: ConversationStatus.completed,
        isLocked: locked);

    testWidgets('reprocess disables the row while in flight, then shows and hands over the result', (tester) async {
      final pending = Completer<ServerConversation?>();
      final requested = <String>[];
      final conversations = _Conversations();
      addTearDown(conversations.dispose);
      final sync = _Sync()
        ..pointers = [
          SyncedConversationPointer(
              type: SyncedConversationType.updatedConversation,
              index: 0,
              key: DateTime(2026, 10, 4),
              conversation: conversation('updated', 'Before')),
          SyncedConversationPointer(
              type: SyncedConversationType.newConversation,
              index: 0,
              key: DateTime(2026, 10, 4),
              conversation: conversation('locked', 'Private title', locked: true)),
        ];
      addTearDown(sync.dispose);
      final host = await _pump(tester, SyncedConversationsPage(reprocessConversation: (id) {
        requested.add(id);
        return pending.future;
      }), sync, providers: [ChangeNotifierProvider<ConversationProvider>.value(value: conversations)]);

      expect(_sections(tester).map((section) => section.title), [_l10n.updatedConversations, _l10n.newConversations]);
      expect(nativeProjectedRow(tester, 'synced_conversation:0:updated').title, 'Before');
      expect(nativeProjectedRow(tester, 'synced_conversation:1:locked').title, _l10n.conversations,
          reason: 'Locked content never crosses the bridge');
      expect(_rowIds(tester), isNot(contains('synced_conversation:1:locked:reprocess')));

      unawaited(host.sendFromNative(host.created.last,
          const MethodCall('action', {'id': 'synced_conversation:0:updated:reprocess', 'value': null})));
      await NativeTestHost.settle(tester);
      expect(requested, ['updated']);
      expect(nativeProjectedRow(tester, 'synced_conversation:0:updated:reprocess').projection['enabled'], false);
      expect(nativeProjectedRow(tester, 'synced_conversation:0:updated').subtitle, _l10n.processing);
      expect(nativeProjectedRow(tester, 'synced_conversation:0:updated').options, isEmpty);

      pending.complete(conversation('updated', 'After'));
      await NativeTestHost.settle(tester);
      expect(nativeProjectedRow(tester, 'synced_conversation:0:updated').title, 'After');
      expect(nativeProjectedRow(tester, 'synced_conversation:0:updated:reprocess').projection['enabled'], true);
      expect(conversations.updated.map((c) => c.structured.title), ['After']);
    });
  });

  group('AutoSyncPage', () {
    testWidgets('projects 200 recordings, then more as the end comes into view', (tester) async {
      final sync = _Sync()..wals = [for (var i = 0; i < 450; i++) _wal(i, status: WalStatus.synced)];
      addTearDown(sync.dispose);
      final host = await _pump(tester, const AutoSyncPage(), sync);
      await tester.pump(const Duration(milliseconds: 100));
      await NativeTestHost.settle(tester);

      int walRows() => _rowIds(tester).where((id) => RegExp(r'^offline_wal:[^:]+:\d+$').hasMatch(id)).length;
      expect(walRows(), 200);
      await _send(tester, host, '_visible:offline_more');
      expect(walRows(), 400);
      await _send(tester, host, '_visible:offline_more');
      expect(walRows(), 450);
      expect(_rowIds(tester), isNot(contains('offline_more')));
    });

    testWidgets('the info sheet is a native modal with numbered steps and the footnote', (tester) async {
      final sync = _Sync();
      addTearDown(sync.dispose);
      final presented = _answerPresentations((_) => {'action': null, 'reason': 'cancel'});
      final host = await _pump(tester, const AutoSyncPage(), sync);
      await _send(tester, host, 'offline_info');
      final snapshot = presented.single;
      expect(snapshot['title'], _l10n.howSyncingWorks);
      final section = (snapshot['sections'] as List).single as Map;
      final rows = (section['rows'] as List).cast<Map>();
      expect(rows.map((row) => row['title']), [
        _l10n.syncFlowIntro,
        '1. ${_l10n.syncStepUpload}',
        '2. ${_l10n.syncStepProcess}',
        '3. ${_l10n.syncStepBackedUp}',
      ]);
      expect(rows[1]['subtitle'], _l10n.syncStepUploadDesc);
      expect(section['footer'], _l10n.syncFailureFootnote);
      expect((snapshot['toolbar'] as List).cast<Map>().single['id'], 'sync_info_done');
      expect(find.text(_l10n.syncFlowIntro), findsNothing, reason: 'The Flutter sheet is not shown as well');
    });
  });
}
