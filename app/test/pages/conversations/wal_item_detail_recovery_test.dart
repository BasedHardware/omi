import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/wal_item_detail/wal_item_detail_page.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/widgets/waveform_section.dart';

class _Sync extends ChangeNotifier implements SyncProvider {
  final requests = <Completer<List<double>?>>[];
  final played = <Wal>[];
  final shared = <Wal>[];
  @override
  Future<void> toggleWalPlayback(Wal wal) async => played.add(wal);
  @override
  Future<void> shareWalAsWav(Wal wal) async => shared.add(wal);
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

Future<_Sync> _open(WidgetTester tester) async {
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
        storage: WalStorage.disk,
        device: 'synthetic-pendant',
      )),
    ),
  ));
  return sync;
}

void main() {
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
