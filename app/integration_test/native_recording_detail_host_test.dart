import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/pages/conversations/wal_item_detail/wal_item_detail_page.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';

/// One phone-stored recording whose player is a recorder: Play/Pause only toggles [playing].
class _SeededSync extends ChangeNotifier implements SyncProvider {
  _SeededSync(this.wal);

  final Wal wal;
  bool playing = false;
  int toggles = 0;

  @override
  Wal? getWalById(String walId) => walId == wal.id ? wal : null;
  @override
  bool isWalPlaying(String walId) => playing && walId == wal.id;
  @override
  bool get isProcessingAudio => false;
  @override
  String? get currentPlayingWalId => playing ? wal.id : null;
  @override
  bool canPlayOrShareWal(Wal wal) => true;
  @override
  Wal? get failedWal => null;
  @override
  Duration get currentPosition => playing ? const Duration(seconds: 12) : Duration.zero;
  @override
  Duration get totalDuration => playing ? const Duration(seconds: 95) : Duration.zero;
  @override
  double get playbackProgress => 0;
  @override
  Future<List<double>?> getWaveformForWal(String walId) async => [for (var i = 0; i < 300; i++) (i % 17) / 16];
  @override
  Future<void> toggleWalPlayback(Wal wal) async {
    toggles++;
    playing = !playing;
    notifyListeners();
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// Simulator-only: flutter drive --driver integration_test/native_ui_host_driver.dart
/// --target integration_test/native_recording_detail_host_test.dart --flavor dev
/// --dart-define=OMI_APP_PROFILE=local_dev --dart-define=OMI_IOS_SWIFTUI=true -d <simulator-id>
void main() => runNativeHostSuite((checkNativeHost) {
      testWidgets('a seeded recording opens the native detail and Play/Pause reaches the SyncProvider player',
          (tester) async {
        await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
        addTearDown(JourneyHermeticBoot.stop);
        final sync = _SeededSync(Wal(
            timerStart: DateTime(2026, 9, 20, 10).millisecondsSinceEpoch ~/ 1000,
            codec: BleAudioCodec.opus,
            seconds: 95,
            storage: WalStorage.disk,
            status: WalStatus.synced));
        addTearDown(sync.dispose);
        await tester.pumpWidget(nativeHostApp(const Scaffold(body: Center(child: Text('home'))),
            providers: [ChangeNotifierProvider<SyncProvider>.value(value: sync)]));
        unawaited(Navigator.of(tester.element(find.text('home')))
            .push(MaterialPageRoute<void>(builder: (_) => WalItemDetailPage(wal: sync.wal))));
        await tester.pump(const Duration(milliseconds: 500));
        await checkNativeHost(tester, 'native-recording-detail-wal-dark');
        expect(nativeProjectedRow(tester, 'wal_position').points, hasLength(200));

        await nativeProjectedRow(tester, 'wal_play').action!(null);
        await tester.pump(const Duration(milliseconds: 500));
        expect(sync.toggles, 1);
        expect(nativeProjectedRow(tester, 'wal_play').symbol, 'pause.fill');
        expect(nativeProjectedRow(tester, 'wal_position').value, 12.0);

        await nativeProjectedRow(tester, 'wal_play').action!(null);
        await tester.pump(const Duration(milliseconds: 500));
        expect(sync.toggles, 2);
        expect(nativeProjectedRow(tester, 'wal_play').symbol, 'play.fill');
        expect(tester.takeException(), isNull);
      });
    });
