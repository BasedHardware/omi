import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/pages/conversations/recording_detail/recording_detail_sheet.dart';
import 'package:omi/pages/conversations/wal_item_detail/wal_item_detail_page.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/providers/sync_provider.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/platform/platform_manager.dart';

import 'native_test_host.dart';

final _l10n = lookupAppLocalizations(const Locale('en'));
const _config = MethodChannel('com.omi.native_ui/config');

/// Seeded playback and transfer state; every command the page sends is recorded, none runs.
class _FakeSync extends ChangeNotifier implements SyncProvider {
  _FakeSync(this.wal);

  Wal wal;
  bool playing = false, processing = false, canPlay = true;
  Duration position = Duration.zero, total = Duration.zero;
  double progress = 0;
  List<double>? levels = [0.2, 0.4, 0.8, 0.1];
  Completer<void>? transferGate;
  final calls = <String>[];

  void change(void Function() update) {
    update();
    notifyListeners();
  }

  @override
  Wal? getWalById(String walId) => walId == wal.id ? wal : null;
  @override
  bool isWalPlaying(String walId) => playing && walId == wal.id;
  @override
  bool get isProcessingAudio => processing;
  @override
  String? get currentPlayingWalId => playing || processing ? wal.id : null;
  @override
  bool canPlayOrShareWal(Wal wal) => canPlay;
  @override
  Wal? get failedWal => null;
  @override
  Duration get currentPosition => position;
  @override
  Duration get totalDuration => total;
  @override
  double get playbackProgress => 0;
  @override
  double get walsSyncedProgress => progress;
  @override
  Future<List<double>?> getWaveformForWal(String walId) async => levels;
  @override
  Future<void> toggleWalPlayback(Wal wal) async => calls.add('toggle');
  @override
  Future<void> seekToPosition(Duration position) async => calls.add('seek:${position.inMilliseconds}');
  @override
  Future<void> skipForward({Duration duration = const Duration(seconds: 10)}) async => calls.add('forward');
  @override
  Future<void> skipBackward({Duration duration = const Duration(seconds: 10)}) async => calls.add('back');
  @override
  Future<void> shareWalAsWav(Wal wal) async => calls.add('share');
  @override
  Future<void> transferWalToPhone(Wal wal) async {
    calls.add('transfer');
    await transferGate?.future;
  }

  @override
  void cancelSync() => calls.add('cancel');
  @override
  Future<void> deleteWal(Wal wal) async => calls.add('delete');
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

/// One batch recording with seeded player state; uploads answer [outcome] and are counted.
class _FakeRecordings extends ChangeNotifier implements LocalRecordingsProvider {
  _FakeRecordings(this.recording);

  LocalRecording recording;
  bool playing = false, canPlayValue = true, preparing = false;
  Duration position = Duration.zero, total = Duration.zero;
  LocalUploadOutcome outcome = LocalUploadOutcome.started;
  final calls = <String>[];

  void change(void Function() update) {
    update();
    notifyListeners();
  }

  @override
  LocalRecording? getById(String id) => id == recording.id ? recording : null;
  @override
  bool isPlaying(LocalRecording r) => playing;
  @override
  bool canPlay(LocalRecording r) => canPlayValue;
  @override
  bool get isProcessingAudio => false;
  @override
  bool get isPreparingShare => preparing;
  @override
  Duration get currentPosition => position;
  @override
  Duration get totalDuration => total;
  @override
  double get playbackProgress => 0;
  @override
  Future<List<double>?> getWaveform(LocalRecording r) async => [0.1, 0.5, 0.25];
  @override
  Future<void> togglePlayback(LocalRecording r) async => calls.add('toggle');
  @override
  Future<void> seekTo(Duration position) async => calls.add('seek:${position.inMilliseconds}');
  @override
  Future<void> skipForward() async => calls.add('forward');
  @override
  Future<void> skipBackward() async => calls.add('back');
  @override
  Future<void> share(LocalRecording r) async => calls.add('share');
  @override
  Future<void> delete(LocalRecording r) async => calls.add('delete');
  @override
  Future<LocalUploadOutcome> upload(LocalRecording rec) async {
    calls.add('upload');
    return outcome;
  }

  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

Wal _wal({WalStorage storage = WalStorage.disk, int seconds = 60}) => Wal(
    timerStart: 1790000000,
    codec: BleAudioCodec.opus,
    seconds: seconds,
    storage: storage,
    device: 'omi-device-1',
    deviceModel: 'Omi DevKit 2');

LocalRecording _recording({LocalRecordingState state = LocalRecordingState.pending}) => LocalRecording(
    fileName: 'recording_fs320_1790000000.bin',
    filePath: '/inert/recording.bin',
    timerStart: 1790000000,
    codec: BleAudioCodec.opus,
    frameSize: 320,
    sizeBytes: 64000,
    seconds: 45,
    state: state);

/// The row [id] as the mounted surfaces dispatch it (the topmost one wins), or null.
NativeRow? _row(WidgetTester tester, String id) {
  NativeRow? match;
  for (final surface in tester.stateList<State<IosNativeSurface>>(find.byType(IosNativeSurface))) {
    for (final row in IosNativeSurface.debugDispatchRows(surface)) {
      if (row.id == id) match = row;
    }
  }
  return match;
}

Future<Object?> _send(NativeTestHost host, String id, [Object? value]) async {
  final reply = await host.sendFromNative(host.created.last, MethodCall('action', {'id': id, 'value': value}));
  return const StandardMethodCodec().decodeEnvelope(reply!);
}

final _refused = throwsA(isA<PlatformException>().having((error) => error.code, 'code', 'invalid_native_action'));

/// Answers each 'present' with [reply] (a [PlatformException] is thrown) and records the snapshots.
List<Map> _present(Object? Function(Map snapshot) reply) {
  final presented = <Map>[];
  final messenger = TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger;
  messenger.setMockMethodCallHandler(_config, (call) async {
    if (call.method != 'present') return null;
    final snapshot = (call.arguments as Map)['snapshot'] as Map;
    presented.add(snapshot);
    final answer = reply(snapshot);
    if (answer is PlatformException) throw answer;
    return answer;
  });
  addTearDown(() => messenger.setMockMethodCallHandler(_config, null));
  return presented;
}

List<String> _titles(Map snapshot) => [
      for (final section in (snapshot['sections'] as List).cast<Map>())
        for (final row in (section['rows'] as List).cast<Map>()) row['title'] as String,
    ];

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  /// Pushes the detail page over a home route, so pops are observable.
  Future<void> pumpWalDetail(WidgetTester tester, _FakeSync sync) async {
    await tester.pumpWidget(ChangeNotifierProvider<SyncProvider>.value(
        value: sync, child: NativeTestHost.app(const Scaffold(body: Center(child: Text('home'))))));
    unawaited(Navigator.of(tester.element(find.text('home')))
        .push(MaterialPageRoute<void>(builder: (_) => WalItemDetailPage(wal: sync.wal))));
    await tester.pumpAndSettle();
    await NativeTestHost.settle(tester);
  }

  group('nativeWaveformPoints and nativePlaybackMaximum', () {
    test('clamp non-finite levels, keep at most 200 bars and stay within the duration', () {
      final points = nativeWaveformPoints([double.nan, double.infinity, -0.5, ...List.filled(997, 0.25)], 30);
      expect(points, hasLength(nativeWaveformLimit));
      expect(points.map((point) => point['y'] as double), everyElement(inInclusiveRange(0, 1)));
      expect(points.map((point) => point['x'] as double), everyElement(inExclusiveRange(0, 30)));
      expect(points.map((point) => point['x']).toSet(), hasLength(nativeWaveformLimit));
      expect(points.first['label'], '');
      expect(points.first['y'], 1.0, reason: 'The first span holds the loudest (absolute) level');
    });

    test('omit the waveform for a degenerate duration or no levels', () {
      expect(nativeWaveformPoints([0.5], double.nan), isEmpty);
      expect(nativeWaveformPoints([0.5], double.infinity), isEmpty);
      expect(nativeWaveformPoints([0.5], 0), isEmpty);
      expect(nativeWaveformPoints(null, 10), isEmpty);
      expect(nativeWaveformPoints([double.nan, 0], 10).map((point) => point['y']), [0.0, 0.0]);
      expect(nativePlaybackMaximum(Duration.zero, 0), isNull);
      expect(nativePlaybackMaximum(const Duration(seconds: 90), 60), 90);
      expect(nativePlaybackMaximum(Duration.zero, 60), 60);
    });
  });

  group('WalItemDetailPage', () {
    testWidgets('flag off keeps the classic page without a native surface', (tester) async {
      final sync = _FakeSync(_wal());
      await pumpWalDetail(tester, sync);
      expect(find.byType(IosNativeSurface), findsNothing);
      expect(find.text(_l10n.recordingDetails), findsOneWidget);
    });

    testWidgets('transfer mode projects status, progress and Transfer/Cancel; menu options follow state',
        (tester) async {
      final host = NativeTestHost.install();
      final sync = _FakeSync(_wal(storage: WalStorage.sdcard));
      await pumpWalDetail(tester, sync);
      expect(find.byType(UiKitView), findsOneWidget);
      expect(_row(tester, 'wal_storage')!.symbol, 'sdcard');
      expect(_row(tester, 'wal_storage')!.title, _l10n.storedOnDevice(_l10n.storageLocationSdCard));
      expect(_row(tester, 'wal_transfer_status')!.title, _l10n.transferRequired);
      expect(_row(tester, 'wal_transfer_progress'), isNull);
      expect(_row(tester, 'wal_cancel_transfer'), isNull);
      expect(_row(tester, 'wal_more')!.options.keys, ['info', 'transfer', 'delete']);
      expect(_row(tester, 'wal_position'), isNull, reason: 'No playback before the transfer');

      sync.change(() {
        sync.wal.isSyncing = true;
        sync.wal.syncSpeedKBps = 12.34;
        sync.wal.syncEtaSeconds = 90;
        sync.progress = 0.42;
      });
      await NativeTestHost.settle(tester);
      final progress = _row(tester, 'wal_transfer_progress')!;
      expect(progress.kind, 'progress');
      expect(progress.value, 0.42);
      expect(progress.subtitle, startsWith('42% · 12.3 KB/s · '));
      expect(_row(tester, 'wal_transfer'), isNull);
      expect(_row(tester, 'wal_cancel_transfer')!.destructive, true);
      expect(_row(tester, 'wal_more')!.options.keys, ['info'], reason: 'No transfer or delete while transferring');

      sync.change(() => sync.progress = double.nan);
      await NativeTestHost.settle(tester);
      expect(_row(tester, 'wal_transfer_progress')!.value, 0.0, reason: 'A non-finite progress is clamped');
      expect(_row(tester, 'wal_transfer_progress')!.valid, true);

      expect(await _send(host, 'wal_cancel_transfer'), isNull);
      await tester.pumpAndSettle();
      expect(sync.calls, ['cancel']);
      expect(find.byType(WalItemDetailPage), findsNothing);
      expect(find.text(_l10n.transferCancelled), findsOneWidget);
    });

    testWidgets('Transfer to Phone runs through the owner, confirms and pops once', (tester) async {
      final host = NativeTestHost.install();
      final sync = _FakeSync(_wal(storage: WalStorage.flashPage))..transferGate = Completer<void>();
      await pumpWalDetail(tester, sync);
      expect(_row(tester, 'wal_storage')!.symbol, 'memorychip');
      final sent = _send(host, 'wal_transfer');
      await tester.pump();
      expect(sync.calls, ['transfer']);
      // The owner moves the WAL to the phone before its transfer future completes.
      sync.change(() => sync.wal = _wal(storage: WalStorage.disk));
      // The page sees the WAL leave the device (and pops) before the owner's future completes.
      await tester.pump();
      await tester.pump();
      sync.transferGate!.complete();
      await sent;
      await tester.pumpAndSettle();
      expect(find.byType(WalItemDetailPage), findsNothing);
      expect(find.text('home'), findsOneWidget, reason: 'Only the detail route is popped');
      expect(find.text(_l10n.transferCompleteMessage), findsOneWidget);
    });

    testWidgets('pops once on its own when the WAL leaves device storage', (tester) async {
      NativeTestHost.install();
      final sync = _FakeSync(_wal(storage: WalStorage.sdcard));
      await pumpWalDetail(tester, sync);
      sync.change(() => sync.wal = _wal(storage: WalStorage.disk));
      await tester.pump();
      sync.notifyListeners();
      await tester.pumpAndSettle();
      expect(find.byType(WalItemDetailPage), findsNothing);
      expect(find.text('home'), findsOneWidget);
    });

    testWidgets('playback mode projects the slider, waveform and transport; seeking needs playback', (tester) async {
      final host = NativeTestHost.install();
      final sync = _FakeSync(_wal())..levels = [double.nan, ...List.filled(400, 0.3), double.infinity];
      await pumpWalDetail(tester, sync);
      expect(_row(tester, 'wal_storage')!.symbol, 'lock.shield');
      expect(_row(tester, 'wal_more')!.options.keys, ['info', 'share', 'delete']);
      var slider = _row(tester, 'wal_position')!;
      expect(slider.kind, 'slider');
      expect(slider.maximumValue, 60);
      expect(slider.value, 0.0);
      expect(slider.points, hasLength(200));
      expect(slider.subtitle, '0:00 / 1:00');
      expect(slider.projection['enabled'], false);
      await expectLater(_send(host, 'wal_position', 5.0), _refused);
      await expectLater(_send(host, 'wal_back10'), _refused);
      expect(sync.calls, isEmpty);

      expect(await _send(host, 'wal_play'), isNull);
      sync.change(() {
        sync.playing = true;
        sync.position = const Duration(seconds: 3);
        sync.total = const Duration(seconds: 75);
      });
      await NativeTestHost.settle(tester);
      slider = _row(tester, 'wal_position')!;
      expect(slider.maximumValue, 75);
      expect(slider.value, 3.0);
      expect(slider.subtitle, '0:03 / 1:15');
      expect(_row(tester, 'wal_play')!.symbol, 'pause.fill');
      expect(await _send(host, 'wal_position', 5.5), isNull);
      expect(await _send(host, 'wal_back10'), isNull);
      expect(await _send(host, 'wal_fwd10'), isNull);
      await expectLater(_send(host, 'wal_position', 80.0), _refused, reason: 'Beyond the slider range');
      expect(sync.calls, ['toggle', 'seek:5500', 'back', 'forward']);

      sync.change(() => sync.processing = true);
      await NativeTestHost.settle(tester);
      expect(_row(tester, 'wal_play')!.subtitle, _l10n.processing);
      await expectLater(_send(host, 'wal_play'), _refused, reason: 'Disabled while processing');

      // Leaving stops the shared player through its owner.
      expect(await _send(host, 'wal_back'), isNull);
      await tester.pumpAndSettle();
      expect(sync.calls.last, 'toggle');
    });

    testWidgets('a zero duration omits the slider instead of invalidating the surface', (tester) async {
      NativeTestHost.install();
      final sync = _FakeSync(_wal(seconds: 0));
      await pumpWalDetail(tester, sync);
      expect(_row(tester, 'wal_position'), isNull);
      expect(_row(tester, 'wal_play'), isNotNull);
      expect(find.byType(UiKitView), findsOneWidget, reason: 'Still native, not the fallback');
    });

    testWidgets('Share and Info reach their owners; Info falls back to the Flutter dialog', (tester) async {
      final host = NativeTestHost.install();
      final sync = _FakeSync(_wal());
      await pumpWalDetail(tester, sync);
      expect(await _send(host, 'wal_more', 'share'), isNull);
      expect(sync.calls, ['share']);

      final presented = _present((_) => {'action': null, 'values': <String, Object?>{}, 'reason': 'cancel'});
      expect(await _send(host, 'wal_more', 'info'), isNull);
      await tester.pumpAndSettle();
      expect(presented, hasLength(1));
      expect(presented.single['title'], _l10n.recordingInfo);
      expect(
          _titles(presented.single),
          containsAll([
            _l10n.recordingIdLabel,
            _l10n.durationLabel,
            _l10n.deviceModelLabel,
            _l10n.deviceIdLabel,
            _l10n.statusLabel
          ]));
      expect(find.text(_l10n.recordingIdLabel), findsNothing, reason: 'Cancel is handled, not the Flutter path');

      _present((_) => PlatformException(code: 'invalid_native_presentation'));
      expect(await _send(host, 'wal_more', 'info'), isNull);
      await tester.pumpAndSettle();
      expect(find.text(_l10n.recordingIdLabel), findsOneWidget, reason: 'Unpresented: the Flutter dialog');
    });

    testWidgets('Delete confirms, pops the detail and deletes through the owner', (tester) async {
      final host = NativeTestHost.install();
      final sync = _FakeSync(_wal());
      await pumpWalDetail(tester, sync);
      await expectLater(_send(host, 'wal_more', 'bogus'), _refused, reason: 'Only offered options dispatch');
      final presented = _present((_) => {'action': 'confirm', 'values': <String, Object?>{}, 'reason': 'action'});
      expect(await _send(host, 'wal_more', 'delete'), isNull);
      await tester.pumpAndSettle();
      expect(presented.single['title'], _l10n.deleteRecording);
      expect(sync.calls, ['delete']);
      expect(find.byType(WalItemDetailPage), findsNothing);
    });
  });

  group('Recording detail sheet', () {
    Future<void> openSheet(WidgetTester tester, _FakeRecordings recordings) async {
      await tester.pumpWidget(ChangeNotifierProvider<LocalRecordingsProvider>.value(
          value: recordings,
          child: NativeTestHost.app(Scaffold(
              body: Builder(
                  builder: (context) => TextButton(
                      onPressed: () =>
                          showRecordingDetailSheet(context, recordings.recording, nativeContentForTest: true),
                      child: const Text('open')))))));
      await tester.tap(find.text('open'));
      await tester.pumpAndSettle();
      await NativeTestHost.settle(tester);
    }

    testWidgets('projects player, transport, process and menu; seek needs playback', (tester) async {
      final host = NativeTestHost.install();
      final recordings = _FakeRecordings(_recording());
      await openSheet(tester, recordings);
      expect(find.byType(UiKitView), findsOneWidget);
      expect(_row(tester, 'rec_more')!.options.keys, ['share', 'info', 'delete']);
      final slider = _row(tester, 'rec_position')!;
      expect(slider.maximumValue, 45);
      expect(slider.points, hasLength(3));
      expect(slider.subtitle, '0:00 / 0:45');
      await expectLater(_send(host, 'rec_position', 4.0), _refused);
      expect(_row(tester, 'rec_process')!.title, _l10n.processNow);

      expect(await _send(host, 'rec_play'), isNull);
      recordings.change(() {
        recordings.playing = true;
        recordings.position = const Duration(seconds: 2);
        recordings.total = const Duration(seconds: 50);
      });
      await tester.pump(const Duration(milliseconds: 200));
      await NativeTestHost.settle(tester);
      expect(_row(tester, 'rec_position')!.value, 2.0);
      expect(_row(tester, 'rec_position')!.maximumValue, 50);
      expect(await _send(host, 'rec_position', 4.0), isNull);
      expect(await _send(host, 'rec_back10'), isNull);
      expect(await _send(host, 'rec_fwd10'), isNull);
      expect(await _send(host, 'rec_more', 'share'), isNull);
      expect(recordings.calls, ['toggle', 'seek:4000', 'back', 'forward', 'share']);

      recordings.change(() => recordings.recording = _recording(state: LocalRecordingState.uploading));
      await tester.pump(const Duration(milliseconds: 200));
      await NativeTestHost.settle(tester);
      expect(_row(tester, 'rec_more')!.options.keys, ['share', 'info'], reason: 'No delete while busy');
      expect(_row(tester, 'rec_process')!.title, _l10n.syncStatusUploaded);
      expect(_row(tester, 'rec_process')!.subtitle, _l10n.processing);
      await expectLater(_send(host, 'rec_process'), _refused);
      // Closing the sheet stops playback through the owner.
      expect(await _send(host, 'rec_close'), isNull);
      for (var frame = 0; frame < 10; frame++) {
        await tester.pump(const Duration(milliseconds: 100));
      }
      expect(find.byType(IosNativeSurface), findsNothing);
      expect(recordings.calls.last, 'toggle');
    });

    testWidgets('preparing a share shows loading and disables every action', (tester) async {
      final host = NativeTestHost.install();
      final recordings = _FakeRecordings(_recording());
      await openSheet(tester, recordings);
      recordings.change(() {
        recordings.playing = true;
        recordings.preparing = true;
      });
      await tester.pump(const Duration(milliseconds: 200));
      await NativeTestHost.settle(tester);
      final surface = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface));
      expect(surface.loading, true);
      expect(surface.loadingLabel, _l10n.preparingAudio);
      for (final id in ['rec_more', 'rec_position', 'rec_back10', 'rec_play', 'rec_fwd10', 'rec_process']) {
        expect(_row(tester, id)!.projection['enabled'], false, reason: id);
      }
      await expectLater(_send(host, 'rec_play'), _refused);
      await expectLater(_send(host, 'rec_more', 'delete'), _refused);
      recordings.playing = false;
    });

    for (final (outcome, message, pops) in [
      (LocalUploadOutcome.fairUseLimited, _l10n.fairUseBudgetExhausted, false),
      (LocalUploadOutcome.backendBusy, _l10n.msgUploadFileFailed, false),
      (LocalUploadOutcome.failed, _l10n.anErrorOccurredTryAgain, false),
      (LocalUploadOutcome.busy, null, false),
      (LocalUploadOutcome.started, null, true),
    ]) {
      testWidgets('Process now handles ${outcome.name} like the Flutter sheet', (tester) async {
        final host = NativeTestHost.install();
        final recordings = _FakeRecordings(_recording())..outcome = outcome;
        await openSheet(tester, recordings);
        expect(await _send(host, 'rec_process'), isNull);
        await tester.pumpAndSettle();
        expect(recordings.calls, ['upload']);
        if (message != null) expect(find.text(message), findsOneWidget);
        if (outcome == LocalUploadOutcome.busy) expect(find.byType(SnackBar), findsNothing);
        expect(find.byType(IosNativeSurface), pops ? findsNothing : findsOneWidget);
      });
    }

    testWidgets('Delete pops the sheet after confirmation; Info uses the label modal', (tester) async {
      final host = NativeTestHost.install();
      final recordings = _FakeRecordings(_recording());
      await openSheet(tester, recordings);
      final presented = _present((snapshot) => snapshot['title'] == _l10n.recordingInfo
          ? {'action': null, 'values': <String, Object?>{}, 'reason': 'cancel'}
          : {'action': 'confirm', 'values': <String, Object?>{}, 'reason': 'action'});
      expect(await _send(host, 'rec_more', 'info'), isNull);
      await tester.pumpAndSettle();
      expect(_titles(presented.last), [
        _l10n.dateTimeLabel,
        _l10n.durationLabel,
        _l10n.audioFormatLabel,
        _l10n.estimatedSizeLabel,
      ]);
      expect(await _send(host, 'rec_more', 'delete'), isNull);
      await tester.pumpAndSettle();
      expect(presented.last['title'], _l10n.deleteRecording);
      expect(recordings.calls, ['delete']);
      expect(find.byType(IosNativeSurface), findsNothing);
    });
  });
}
