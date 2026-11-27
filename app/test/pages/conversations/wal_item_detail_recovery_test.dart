import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/wal_item_detail/wal_item_detail_page.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/devices/connectors/device_connection.dart';
import 'package:omi/widgets/waveform_section.dart';

class _Sync extends ChangeNotifier implements SyncProvider {
  final requests = <Completer<List<double>?>>[];
  final played = <Wal>[];
  final shared = <Wal>[];
  final deleted = <Wal>[];
  final wals = <Wal>[];
  final transferDone = Completer<void>();
  bool failDelete = false;
  bool retainOnDelete = false;
  Wal? transferring;
  @override
  double get walsSyncedProgress => 0.87;
  @override
  Future<void> transferWalToPhone(Wal wal) {
    transferring = wal;
    wal.isSyncing = true;
    notifyListeners();
    return transferDone.future;
  }

  void reportTransfer(double fraction) {
    transferring!
      ..deviceDownloadFraction = fraction
      ..syncSpeedKBps = 50;
    notifyListeners();
  }

  @override
  Future<void> toggleWalPlayback(Wal wal) async => played.add(wal);
  @override
  Future<void> shareWalAsWav(Wal wal) async => shared.add(wal);
  @override
  Future<void> deleteWal(Wal wal, {String? firmwareVersion, bool refreshDevice = true}) async {
    deleted.add(wal);
    if (failDelete) throw StateError('simulated device delete failure');
    if (!retainOnDelete) wals.removeWhere((item) => item.id == wal.id && item.storage == wal.storage);
  }

  @override
  List<Wal> get allWals => wals;

  @override
  Future<void> discoverDeviceWals({String? firmwareVersion}) async {}

  @override
  Wal? getWalById(String id) => null;
  @override
  Future<List<double>?> getWaveformForWal(String id) {
    final request = Completer<List<double>?>();
    requests.add(request);
    return request.future;
  }

  @override
  bool isWalPlaying(String id) => false;
  @override
  bool get isProcessingAudio => false;
  @override
  bool canPlayOrShareWal(Wal wal) => true;
  @override
  Wal? get failedWal => null;
  @override
  Duration get currentPosition => Duration.zero;
  @override
  Duration get totalDuration => const Duration(seconds: 30);
  @override
  double get playbackProgress => 0;
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

class _Device extends ChangeNotifier implements DeviceProvider {
  @override
  String currentFirmwareVersion = 'Unknown';
  @override
  bool isConnected = false;
  @override
  RingStatus? get ringStatus => null;
  @override
  Future<void> refreshRingStorageStatus() async {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Future<_Sync> _open(WidgetTester tester, {WalStorage storage = WalStorage.disk}) async {
  final sync = _Sync();
  tester.view.physicalSize = const Size(1170, 2532);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(ChangeNotifierProvider<SyncProvider>.value(
    value: sync,
    child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: WalItemDetailPage(
          wal: Wal(
        timerStart: 1700000000,
        codec: BleAudioCodec.opus,
        seconds: 30,
        status: WalStatus.miss,
        storage: storage,
        device: 'synthetic-pendant',
      )),
    ),
  ));
  return sync;
}

Future<_Sync> _openDeleteFlow(WidgetTester tester, {required bool failDelete}) async {
  final sync = _Sync()..failDelete = failDelete;
  final wal = Wal(
    timerStart: 1700000000,
    codec: BleAudioCodec.opus,
    seconds: 30,
    status: WalStatus.miss,
    storage: WalStorage.sdcard,
    device: 'synthetic-pendant',
  );
  sync.wals.add(wal);
  final device = _Device();
  addTearDown(sync.dispose);
  addTearDown(device.dispose);
  tester.view.physicalSize = const Size(1170, 2532);
  tester.view.devicePixelRatio = 3;
  addTearDown(tester.view.reset);
  await tester.pumpWidget(MultiProvider(
    providers: [
      ChangeNotifierProvider<SyncProvider>.value(value: sync),
      ChangeNotifierProvider<DeviceProvider>.value(value: device),
    ],
    child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Builder(
        builder: (context) => Scaffold(
          body: Column(
            children: [
              const Text('Previous screen'),
              TextButton(
                onPressed: () => Navigator.of(context).push(
                  MaterialPageRoute<void>(builder: (_) => WalItemDetailPage(wal: wal)),
                ),
                child: const Text('Open recording'),
              ),
            ],
          ),
        ),
      ),
    ),
  ));
  await tester.tap(find.text('Open recording'));
  await tester.pumpAndSettle();
  expect(tester.takeException(), isNull);
  return sync;
}

void main() {
  testWidgets('Transfer to Phone shows only the selected recording’s measured progress', (tester) async {
    final sync = await _open(tester, storage: WalStorage.sdcard);
    await tester.tap(find.text('Transfer to Phone'));
    await tester.pump();
    LinearProgressIndicator indicator() => tester.widget(find.byType(LinearProgressIndicator));

    // A different background sync is at 87%. This transfer has no measurement yet.
    expect(indicator().value, isNull);
    expect(find.textContaining('%'), findsNothing);
    sync.reportTransfer(0);
    await tester.pump();
    expect(indicator().value, 0);
    expect(find.text('0%'), findsOneWidget);
    sync.reportTransfer(0.38);
    await tester.pump();
    expect(indicator().value, 0.38);
    expect(find.text('38%'), findsOneWidget);
    expect(find.text('50.0 KB/s'), findsOneWidget);

    // The same progress row must remain readable with a short viewport.
    tester.view.physicalSize = const Size(2400, 1500);
    await tester.pump();
    expect(tester.takeException(), isNull);
    await tester.ensureVisible(find.text('38%'));
    expect(find.text('38%').hitTestable(), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
    sync.transferDone.complete();
  });

  testWidgets('waveform failure ends loading and retry renders recovered waveform', (tester) async {
    final sync = await _open(tester);
    expect(tester.widget<WaveformSection>(find.byType(WaveformSection)).isProcessingWaveform, isTrue);
    sync.requests.single.completeError(const FileSystemException('synthetic read failure'));
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(find.text('Error loading audio'), findsOneWidget);
    // Waveform preparation is independent of playback and export. Neither
    // operation should require a paid account or a successfully drawn preview.
    await tester.tap(find.byWidgetPredicate((w) => w is FaIcon && w.icon == FontAwesomeIcons.play.data));
    await tester.pump();
    expect(sync.played, hasLength(1));
    await tester.tap(find.byIcon(Icons.more_horiz));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Share Recording'));
    await tester.pumpAndSettle();
    expect(sync.shared.single, same(sync.played.single));
    await tester.tap(find.text('Try Again'));
    await tester.pump();
    expect(sync.requests, hasLength(2));
    sync.requests.last.complete([0.1, 0.6, 0.2]);
    await tester.pump();
    expect(find.text('Error loading audio'), findsNothing);
    expect(tester.widget<WaveformSection>(find.byType(WaveformSection)).waveformData, [0.1, 0.6, 0.2]);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('leaving while waveform fails does not report an uncaught error', (tester) async {
    final sync = await _open(tester);
    await tester.pumpWidget(const SizedBox.shrink());
    sync.requests.single.completeError(StateError('WAL no longer listed'));
    await tester.pump();
    expect(tester.takeException(), isNull);
  });

  testWidgets('successful waveform generation renders normally', (tester) async {
    final sync = await _open(tester);
    sync.requests.single.complete([0.1, 0.4]);
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(tester.widget<WaveformSection>(find.byType(WaveformSection)).waveformData, [0.1, 0.4]);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('failed recording deletion keeps the detail page open and reports the failure', (tester) async {
    final sync = await _openDeleteFlow(tester, failDelete: true);
    final l10n = AppLocalizations.of(tester.element(find.byType(WalItemDetailPage)))!;

    await tester.tap(find.byIcon(Icons.more_horiz));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.tap(find.text(l10n.deleteRecording));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.tap(find.text(l10n.delete));
    await tester.pumpAndSettle();

    expect(sync.deleted, hasLength(1));
    expect(find.byType(WalItemDetailPage), findsOneWidget);
    expect(find.text(l10n.failedToDeleteSomeItems), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });

  testWidgets('successful recording deletion returns to the previous screen', (tester) async {
    final sync = await _openDeleteFlow(tester, failDelete: false);
    final l10n = AppLocalizations.of(tester.element(find.byType(WalItemDetailPage)))!;

    await tester.tap(find.byIcon(Icons.more_horiz));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.tap(find.text(l10n.deleteRecording));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);
    await tester.tap(find.text(l10n.delete));
    await tester.pumpAndSettle();
    expect(tester.takeException(), isNull);

    expect(sync.deleted, hasLength(1));
    expect(find.byType(WalItemDetailPage), findsNothing);
    expect(find.text('Previous screen'), findsOneWidget);
  });

  testWidgets('recording detail stays open when deletion returns but retains the WAL', (tester) async {
    final sync = await _openDeleteFlow(tester, failDelete: false);
    sync.retainOnDelete = true;
    final l10n = AppLocalizations.of(tester.element(find.byType(WalItemDetailPage)))!;

    await tester.tap(find.byIcon(Icons.more_horiz));
    await tester.pumpAndSettle();
    await tester.tap(find.text(l10n.deleteRecording));
    await tester.pumpAndSettle();
    await tester.tap(find.text(l10n.delete));
    await tester.pumpAndSettle();

    expect(sync.deleted, hasLength(1));
    expect(sync.allWals, hasLength(1));
    expect(find.byType(WalItemDetailPage), findsOneWidget);
    expect(find.text(l10n.failedToDeleteSomeItems), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('unavailable audio shows retry and repeated failures remain retryable', (tester) async {
    final sync = await _open(tester);
    sync.requests.single.complete(null);
    await tester.pump();
    expect(find.text('Error loading audio'), findsOneWidget);
    await tester.tap(find.text('Try Again'));
    await tester.pump();
    sync.requests.last.completeError(const FileSystemException('still unavailable'));
    await tester.pump();
    expect(tester.takeException(), isNull);
    expect(find.text('Try Again'), findsOneWidget);
    await tester.pumpWidget(const SizedBox.shrink());
  });
}
