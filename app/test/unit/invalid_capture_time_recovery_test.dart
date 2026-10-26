import 'dart:io';

import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/services/wals/local_wal_sync.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/services/wals/wal_interfaces.dart';
import 'package:omi/utils/wal_file_manager.dart';

/// `invalid_capture_time` recovery: the server refuses a recording's claimed
/// capture time (HTTP 400, by bounded code or the deployed route's exact
/// detail line), not its audio. Audio is never deleted for its claimed time;
/// a fragment is re-stamped only when contiguous audio of the same source run
/// proves when it began, once, crash-safely; anything else stays as an
/// attention row with the reason kept.

class _MockListener implements IWalSyncListener {
  @override
  void onWalUpdated() {}

  @override
  void onWalSynced(Wal wal, {ServerConversation? conversation}) {}
}

Wal _wal({
  required int timerStart,
  int seconds = 60,
  String? filePath,
  bool restamped = false,
  String? clockRun,
  String? recordingSessionId,
  String? captureRoot,
  int? sourceClockEpoch,
  int? sourceFrameStart,
  int? totalFrames,
}) {
  final name = filePath ?? 'audio_omi_opus_16000_1_fs160_$timerStart.bin';
  return Wal(
    timerStart: timerStart,
    codec: BleAudioCodec.opus,
    seconds: seconds,
    status: WalStatus.miss,
    storage: WalStorage.disk,
    device: 'omi',
    filePath: name,
    captureTimeRestamped: restamped,
    clockRun: clockRun,
    recordingSessionId: recordingSessionId,
    captureRoot: captureRoot,
    sourceClockEpoch: sourceClockEpoch,
    sourceFrameStart: sourceFrameStart,
    totalFrames: totalFrames ?? seconds * 100, // opus frames per second
  );
}

Wal _neighbour({
  required int timerStart,
  required int seconds,
  String? clockRun,
  String? recordingSessionId,
  WalStatus status = WalStatus.uploaded,
}) =>
    _wal(
      timerStart: timerStart,
      seconds: seconds,
      clockRun: clockRun,
      recordingSessionId: recordingSessionId,
    ).letStatus(status);

extension _WalStatusLet on Wal {
  Wal letStatus(WalStatus s) {
    status = s;
    return this;
  }
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;
  late LocalWalSyncImpl sync;
  late List<List<String>> uploadAttempts;
  late Object? refuseWith;
  int acceptAfter = 0;
  Future<void> Function(List<Wal> wals)? persistOverride;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    tempDir = await Directory.systemTemp.createTemp('invalid_capture_time_');
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      (MethodCall call) async {
        if (call.method == 'getApplicationDocumentsDirectory') return tempDir.path;
        return null;
      },
    );
    await WalFileManager.init();
    SyncRateLimiter.instance.clear();
    uploadAttempts = [];
    refuseWith = null;
    acceptAfter = 0;
    persistOverride = null;
    sync = LocalWalSyncImpl(
      _MockListener(),
      uploadGate: SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        uploader: (files,
            {onUploadProgress,
            conversationId,
            captureEvidence,
            recordingSessionId,
            audioStartSeconds,
            audioEndSeconds,
            claimLiveCapture = false,
            geolocation}) async {
          uploadAttempts.add(files.map((file) => file.uri.pathSegments.last).toList());
          if (refuseWith != null && uploadAttempts.length <= acceptAfter) {
            throw refuseWith!;
          }
          return UploadFilesResult.queued('job-${uploadAttempts.length}');
        },
        fairUseStatusLoader: () async => {'stage': 'none'},
      ),
      persistWals: (wals) async {
        final override = persistOverride;
        if (override != null) {
          await override(wals);
        } else {
          await WalFileManager.saveWals(wals);
        }
      },
    );
  });

  tearDown(() async {
    TestDefaultBinaryMessengerBinding.instance.defaultBinaryMessenger.setMockMethodCallHandler(
      const MethodChannel('plugins.flutter.io/path_provider'),
      null,
    );
    SyncRateLimiter.instance.clear();
    if (tempDir.existsSync()) tempDir.deleteSync(recursive: true);
  });

  Future<File> writeAudio(Wal wal) async {
    final file = File('${tempDir.path}/${wal.filePath}');
    await file.writeAsBytes([0xAA, 0xBB]);
    return file;
  }

  test('a one-second fragment is never deleted: it stays as an attention row', () async {
    // One second of audio — the splice wreckage a corrupted-marker split
    // produced by the thousand. Deleting it quietly lost audio the user never
    // consented to lose, so it stays a row the user decides about.
    final wal = _wal(timerStart: 2051222400, seconds: 1); // claimed 2035
    final file = await writeAudio(wal);
    sync.testWals = [wal];
    refuseWith = const SyncInvalidCaptureTimeException(serverReason: 'invalid timestamp');
    acceptAfter = 99;

    await sync.syncAll();

    expect(wal.status, WalStatus.uploadRejected, reason: 'no proven neighbour: terminal with the reason kept');
    expect(wal.uploadRejectionReason, WalUploadRejection.invalidCaptureTime);
    expect(await sync.getAllWals(), hasLength(1), reason: 'the row stays for the user to delete');
    expect(file.existsSync(), isTrue, reason: 'an invalid_capture_time refusal never deletes audio');
  });

  test('a fragment with no proven contiguous neighbour keeps its own time and file', () async {
    // A same-device neighbour with a plausible end used to win by being the
    // latest plausible audio on the device; without a shared run it proves
    // nothing about when this fragment was recorded.
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final wal = _wal(timerStart: 2051222400, seconds: 60); // claimed 2035
    final file = await writeAudio(wal);
    final bystander = _neighbour(timerStart: now - 600, seconds: 60);
    sync.testWals = [wal, bystander];
    refuseWith = const SyncInvalidCaptureTimeException(serverReason: 'invalid timestamp');
    acceptAfter = 99;

    await sync.syncAll();

    expect(wal.status, WalStatus.uploadRejected);
    expect(wal.uploadRejectionReason, WalUploadRejection.invalidCaptureTime);
    expect(wal.timerStart, 2051222400, reason: 'no date is invented for unproven audio');
    expect(wal.filePath, file.uri.pathSegments.last, reason: 'the file keeps its own name');
    expect(file.existsSync(), isTrue);
    expect(uploadAttempts, hasLength(1), reason: 'nothing is re-offered');
  });

  test('a fragment of a shared clock run is re-stamped at its run predecessor and re-offered once', () async {
    // Two chunks of one estimated run: the predecessor ends exactly where this
    // chunk claims to begin, so the run's own clock proves the start.
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final predecessor = _neighbour(timerStart: now - 3600, seconds: 120, clockRun: 'run1');
    final wal = _wal(timerStart: now - 3600 + 120 + 45, seconds: 60, clockRun: 'run1', restamped: false);
    expect(wal.timerStart < now, isTrue, reason: 'fixture: a plausible claimed start the server still refuses');
    await writeAudio(predecessor);
    await writeAudio(wal);
    sync.testWals = [wal, predecessor];
    // The claimed time is plausible to the fixture uploader; the refusal is
    // what carries the information, so refuse every attempt after wiring the
    // exception for exactly one upload.
    refuseWith = const SyncInvalidCaptureTimeException(serverReason: 'invalid timestamp');
    acceptAfter = 1;

    await sync.syncAll();

    expect(uploadAttempts, hasLength(2), reason: 'the restamped file is re-offered in the same drain');
    expect(uploadAttempts.first, isNot(uploadAttempts.last), reason: 'the re-offer carries a renamed file');
    expect(wal.status, isNot(WalStatus.uploadRejected), reason: 'the re-stamped upload was accepted');
    expect(wal.timerStart, predecessor.timerStart + predecessor.seconds,
        reason: 'the re-stamp is the run predecessor\'s end');
    expect(wal.captureTimeRestamped, isTrue);
    expect(wal.clockRun, isNotNull, reason: 'an estimated time names its clock run');
    expect(File('${tempDir.path}/${wal.filePath}').existsSync(), isTrue);
    expect(uploadAttempts.last, [wal.filePath]);
  });

  test('a second invalid_capture_time refusal after the one re-stamp is terminal with the reason kept', () async {
    final wal = _wal(timerStart: 1800000000, seconds: 60, restamped: true);
    await writeAudio(wal);
    sync.testWals = [wal];
    refuseWith = const SyncInvalidCaptureTimeException(serverReason: 'invalid timestamp');
    acceptAfter = 99;

    await sync.syncAll();

    expect(wal.status, WalStatus.uploadRejected);
    expect(wal.uploadRejectionReason, WalUploadRejection.invalidCaptureTime);
    expect(uploadAttempts, hasLength(1), reason: 'the cap keeps a restamped file from looping');
  });

  test('other 400s stay terminal and keep the server-side classification', () async {
    final wal = _wal(timerStart: 1800000000, seconds: 60);
    await writeAudio(wal);
    sync.testWals = [wal];
    refuseWith = const SyncUploadHttpException(400, 'audio malformed');
    acceptAfter = 99;

    await sync.syncAll();

    expect(wal.status, WalStatus.uploadRejected);
    expect(wal.uploadRejectionReason, WalUploadRejection.serverRefused);
    expect(wal.captureTimeRestamped, isFalse, reason: 'no time repair happens for a non-time refusal');
  });

  group('contiguousCaptureStartSeconds', () {
    const now = 1790000000;

    test('a frame-adjacent predecessor on the source clock names the start', () {
      // Wall-clock dates disagree wildly, but the source's own frame clock
      // proves the chunks are one continuous run: 60 s of opus is 6000 frames.
      final wal = _wal(
        timerStart: 2051222400,
        seconds: 60,
        captureRoot: 'root1',
        sourceClockEpoch: 7,
        sourceFrameStart: 50000,
      );
      final predecessor = _wal(
        timerStart: now - 3600,
        seconds: 60,
        captureRoot: 'root1',
        sourceClockEpoch: 7,
        sourceFrameStart: 50000 - 6000,
      );
      expect(contiguousCaptureStartSeconds(wal, [predecessor], now), now - 3600 + 60);
    });

    test('a shared clock run predecessor within the pause gap qualifies, not the latest device audio', () {
      final wal = _wal(timerStart: 1789999000, clockRun: 'run1');
      final adjacent = _neighbour(timerStart: 1789999000 - 120, seconds: 120, clockRun: 'run1');
      final stranger = _neighbour(timerStart: 1789990000, seconds: 60);
      expect(contiguousCaptureStartSeconds(wal, [stranger, adjacent], now), 1789999000,
          reason: 'the run predecessor\'s end, not the stranger\'s');
    });

    test('a run predecessor across a silence longer than the gap proves nothing', () {
      final wal = _wal(timerStart: 1789999000, clockRun: 'run1');
      final far = _neighbour(timerStart: 1789999000 - 600, seconds: 60, clockRun: 'run1');
      expect(contiguousCaptureStartSeconds(wal, [far], now), isNull);
    });

    test('a predecessor on the same wrong clock (future end) never qualifies', () {
      final wal = _wal(timerStart: 2051222400, clockRun: 'run1');
      final future = _neighbour(timerStart: 2051222340, seconds: 60, clockRun: 'run1');
      expect(contiguousCaptureStartSeconds(wal, [future], now), isNull,
          reason: 'chaining one refused time to another would just be refused again');
    });

    test('no run identity, no neighbour — not even a same-device plausible one', () {
      final wal = _wal(timerStart: 1789999000);
      final bystander = _neighbour(timerStart: 1789998900, seconds: 60);
      expect(contiguousCaptureStartSeconds(wal, [bystander], now), isNull);
    });
  });

  group('crash-safe re-stamp', () {
    test('a failed index save rolls the row back and the audio stays reachable under its old name', () async {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final predecessor = _neighbour(timerStart: now - 3600, seconds: 120, clockRun: 'run1');
      final wal = _wal(timerStart: now - 3600 + 120, seconds: 60, clockRun: 'run1');
      final file = await writeAudio(wal);
      await writeAudio(predecessor);
      sync.testWals = [wal, predecessor];
      refuseWith = const SyncInvalidCaptureTimeException(serverReason: 'invalid timestamp');
      acceptAfter = 99;
      // The restamp's own index save (the snapshot with the new path) fails;
      // every other save reaches the disk as usual.
      persistOverride = (wals) async {
        if (wals.any((w) => w.captureTimeRestamped)) throw const FileSystemException('disk full');
        await WalFileManager.saveWals(wals);
      };

      await sync.syncAll();

      expect(wal.filePath, file.uri.pathSegments.last, reason: 'the row keeps the name the index still has');
      expect(wal.captureTimeRestamped, isFalse);
      expect(file.existsSync(), isTrue, reason: 'the original file was never deleted');
      final reloaded = await WalFileManager.loadWals();
      expect(reloaded.any((w) => w.filePath == file.uri.pathSegments.last), isTrue,
          reason: 'a restart finds the audio under the name the durable index points at');
    });

    test('an interrupted index save after the copy leaves the audio reachable after a restart', () async {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final predecessor = _neighbour(timerStart: now - 3600, seconds: 120, clockRun: 'run1');
      final wal = _wal(timerStart: now - 3600 + 120, seconds: 60, clockRun: 'run1');
      final file = await writeAudio(wal);
      await writeAudio(predecessor);
      sync.testWals = [wal, predecessor];
      refuseWith = const SyncInvalidCaptureTimeException(serverReason: 'invalid timestamp');
      acceptAfter = 99;
      // The restamp's index save writes durably, then control is lost — the
      // crash window between the durable save and the old file's deletion.
      persistOverride = (wals) async {
        await WalFileManager.saveWals(wals);
        if (wals.any((w) => w.captureTimeRestamped)) throw StateError('interrupted');
      };

      await sync.syncAll();

      // Whichever name the durable index settled on, a restart reaches the audio.
      final reloaded = await WalFileManager.loadWals();
      final row = reloaded.firstWhere(
          (w) => w.clockRun == 'run1' && w.captureTimeRestamped || w.filePath == file.uri.pathSegments.last);
      final indexed = File('${tempDir.path}/${row.filePath}');
      expect(indexed.existsSync(), isTrue, reason: 'the index never points at a name whose file was already deleted');
    });

    test('a completed re-stamp deletes the old file and the index names the copy', () async {
      final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
      final predecessor = _neighbour(timerStart: now - 3600, seconds: 120, clockRun: 'run1');
      final wal = _wal(timerStart: now - 3600 + 120, seconds: 60, clockRun: 'run1');
      final oldFile = await writeAudio(wal);
      await writeAudio(predecessor);
      sync.testWals = [wal, predecessor];
      refuseWith = const SyncInvalidCaptureTimeException(serverReason: 'invalid timestamp');
      acceptAfter = 1;

      await sync.syncAll();

      expect(oldFile.existsSync(), isFalse, reason: 'the completed move removes the old name');
      final reloaded = await WalFileManager.loadWals();
      expect(reloaded.any((w) => w.filePath == wal.filePath), isTrue);
      expect(File('${tempDir.path}/${wal.filePath}').existsSync(), isTrue);
    });
  });

  test('a 400 is invalid capture time by bounded code or by the deployed detail line', () {
    http.Response body(String payload) => http.Response(payload, 400);

    // The not-yet-deployed server (PR #23746) names the refusal with a code.
    expect(
        isInvalidCaptureTimeResponse(body('{"detail": "invalid timestamp", "code": "invalid_capture_time"}')), isTrue);
    // The currently deployed server names it only in the detail, with no code.
    expect(isInvalidCaptureTimeResponse(body('{"detail": "Invalid sync file format: invalid timestamp"}')), isTrue);
    // Any other 400 stays a generic refusal.
    expect(isInvalidCaptureTimeResponse(body('{"detail": "Invalid sync file format"}')), isFalse);
    expect(isInvalidCaptureTimeResponse(body('{"detail": "audio malformed"}')), isFalse);
    expect(isInvalidCaptureTimeResponse(body('not json')), isFalse);

    expect(syncUploadErrorCode(body('{"detail": "invalid timestamp", "code": "invalid_capture_time"}')),
        'invalid_capture_time');
    expect(syncUploadErrorCode(body('{"detail": "invalid timestamp"}')), isNull);
    expect(syncUploadErrorReason(body('{"message": "too many files"}')), 'too many files');
    expect(syncUploadErrorReason(body('not json')), isNull);
  });
}
