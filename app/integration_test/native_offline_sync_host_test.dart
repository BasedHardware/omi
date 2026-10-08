import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/models/sync_state.dart';
import 'package:omi/pages/conversations/auto_sync_page.dart';
import 'package:omi/pages/conversations/sync_page.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/recording_transfer_coordinator.dart';
import 'package:omi/services/wals/wal.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';
import 'visual_audit/fakes.dart';

/// Seeded recordings with no BLE or upload behind them; commands are recorded, never performed.
class _SeededSync extends InertSyncProvider {
  _SeededSync(this.wals);

  final List<Wal> wals;
  WalStatusFilter filter = WalStatusFilter.pending;
  final calls = <String>[];

  List<Wal> _where(WalStatus status) => wals.where((wal) => wal.status == status).toList();

  @override
  SyncState get syncState => const SyncState();
  @override
  List<Wal> get allWals => wals;
  @override
  bool get isLoadingWals => false;
  @override
  WalStatusFilter get statusFilter => filter;
  @override
  void setStatusFilter(WalStatusFilter value) {
    filter = value;
    notifyListeners();
  }

  @override
  List<Wal> get pendingWals => _where(WalStatus.miss);
  @override
  List<Wal> get syncedWals => _where(WalStatus.synced);
  @override
  List<Wal> get corruptedWals => _where(WalStatus.corrupted);
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
  List<Wal> get missingWals => pendingWals;
  @override
  List<Wal> get pendingDeletableWals => pendingWals;
  @override
  int get clearableWalsCount => wals.length;
  @override
  List<Wal> walsForDisplayFilter(WalDisplayFilter filter) => wals;
  @override
  List<Wal> get displaySortedWals => wals;
  @override
  String? get syncError => null;
  @override
  Wal? get failedWal => null;
  @override
  bool get isSdCardSyncing => false;
  @override
  Future<void> refreshWals() async {}
  @override
  Future<void> syncWals({WakeTrigger trigger = WakeTrigger.userRetry}) async => calls.add('sync');
}

Wal _wal(int index, WalStatus status) =>
    Wal(timerStart: 1790000000 + index * 3600, codec: BleAudioCodec.opus, seconds: 30, status: status, device: 'phone');

int _rows(WidgetTester tester, RegExp pattern) => [
      for (final surface in tester.stateList<State<IosNativeSurface>>(find.byType(IosNativeSurface)))
        ...IosNativeSurface.debugDispatchRows(surface).where((row) => pattern.hasMatch(row.id)),
    ].length;

void main() {
  runNativeHostSuite((checkNativeHost) {
    testWidgets('native SyncPage renders seeded recordings and opens Manage Storage natively', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final owner = _SeededSync([_wal(0, WalStatus.miss), _wal(1, WalStatus.miss), _wal(2, WalStatus.synced)]);
      addTearDown(owner.dispose);
      await tester.pumpWidget(
          nativeHostApp(const SyncPage(), providers: [ChangeNotifierProvider<SyncProvider>.value(value: owner)]));
      await checkNativeHost(tester, 'native-offline-sync-sync-page-dark');
      final l10n = AppLocalizations.of(tester.element(find.byType(IosNativeSurface)));
      expect(nativeProjectedRow(tester, 'sync_status_title').title, l10n.syncCardReadyCount(2));
      expect(_rows(tester, RegExp(r'^sync_wal:\d+:[^:]+$')), 2);
      expect(owner.calls, isEmpty, reason: 'Rendering status never starts a sync');

      await nativeProjectedRow(tester, 'sync_manage').action!(null);
      await tester.pump(const Duration(seconds: 1));
      await tester.pump(const Duration(seconds: 1));
      expect(nativeProjectedRow(tester, 'storage_clear_all').destructive, true);
      expect(await captureNativeHostScreenshot('native-offline-sync-manage-storage-dark'), isNotEmpty);
      await nativeProjectedRow(tester, 'storage_close').action!(null);
      await tester.pump(const Duration(seconds: 1));
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(tester.takeException(), isNull);
    });

    testWidgets('native Offline Sync opens Manage Storage and grows its recording window on scroll', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      final owner = _SeededSync([for (var i = 0; i < 450; i++) _wal(i, WalStatus.synced)]);
      addTearDown(owner.dispose);
      await tester.pumpWidget(
          nativeHostApp(const AutoSyncPage(), providers: [ChangeNotifierProvider<SyncProvider>.value(value: owner)]));
      await checkNativeHost(tester, 'native-offline-sync-auto-sync-dark');
      final rows = RegExp(r'^offline_wal:[^:]+:\d+$');
      expect(_rows(tester, rows), 200);

      await nativeProjectedRow(tester, 'offline_more').onVisible!(null);
      await tester.pump(const Duration(seconds: 1));
      expect(_rows(tester, rows), 400);
      expect(find.byType(UiKitView), findsOneWidget, reason: 'The grown window stays native');

      await nativeProjectedRow(tester, 'offline_manage').action!(null);
      await tester.pump(const Duration(seconds: 1));
      await tester.pump(const Duration(seconds: 1));
      expect(nativeProjectedRow(tester, 'storage_auto_remove').kind, 'toggle');
      expect(await captureNativeHostScreenshot('native-offline-sync-auto-sync-storage-dark'), isNotEmpty);
      await nativeProjectedRow(tester, 'storage_close').action!(null);
      await tester.pump(const Duration(seconds: 1));
      await tester.pumpWidget(const SizedBox());
      await tester.pump();
      expect(tester.takeException(), isNull);
    });
  });
}
