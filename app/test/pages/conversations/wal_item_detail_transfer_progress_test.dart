import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/wal_item_detail/wal_item_detail_page.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';

class _FakeTransferSync extends ChangeNotifier implements SyncProvider {
  _FakeTransferSync({required this.wal, this.sharedProgress = 0.0});

  final Wal wal;
  final double sharedProgress;

  @override
  Wal? getWalById(String id) => id == wal.id ? wal : null;

  @override
  double get walsSyncedProgress => sharedProgress;

  @override
  bool isWalPlaying(String id) => false;

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<void> _pumpPage(WidgetTester tester, SyncProvider sync, Wal wal) async {
  tester.view.physicalSize = const Size(1170, 2532);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(ChangeNotifierProvider<SyncProvider>.value(
    value: sync,
    child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: WalItemDetailPage(wal: wal),
    ),
  ));
  await tester.pump();
}

void main() {
  testWidgets('renders per-recording download fraction instead of shared walsSyncedProgress', (tester) async {
    final wal = Wal(
      timerStart: 1700000000,
      codec: BleAudioCodec.opus,
      seconds: 600,
      status: WalStatus.miss,
      storage: WalStorage.sdcard,
      device: 'synthetic-cv1',
    )
      ..isSyncing = true
      ..syncSpeedKBps = 55.0
      ..syncEtaSeconds = 900
      ..deviceDownloadFraction = 0.42;

    final sync = _FakeTransferSync(wal: wal, sharedProgress: 0.0);

    await _pumpPage(tester, sync, wal);

    expect(find.text('42%'), findsOneWidget);
    expect(find.text('0%'), findsNothing);
    expect(find.text('55.0 KB/s'), findsOneWidget);
    final bar = tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator));
    expect(bar.value, closeTo(0.42, 1e-6));
  });

  testWidgets('shows explicit unknown progress instead of 0% when deviceDownloadFraction is null', (tester) async {
    final wal = Wal(
      timerStart: 1700000100,
      codec: BleAudioCodec.opus,
      seconds: 600,
      status: WalStatus.miss,
      storage: WalStorage.sdcard,
      device: 'synthetic-cv1',
    )
      ..isSyncing = true
      ..syncSpeedKBps = 50.0
      ..syncEtaSeconds = 900;

    final sync = _FakeTransferSync(wal: wal, sharedProgress: 0.88);

    await _pumpPage(tester, sync, wal);

    expect(find.text('Unknown'), findsOneWidget);
    expect(find.text('0%'), findsNothing);
    expect(find.text('88%'), findsNothing);
    final bar = tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator));
    expect(bar.value, isNull);
  });
}
