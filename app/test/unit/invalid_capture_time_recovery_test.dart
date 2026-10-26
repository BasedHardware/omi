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
/// detail line), not its audio. The app never deletes the file and never
/// renames it — no neighbour estimate, however contiguous, can honestly
/// re-date audio the server just refused — so the row parks on attention with
/// the reason kept, and a retry resends the very same bytes, which a
/// server-side fix can still accept.

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
  String? captureRoot,
  int? sourceClockEpoch,
  int? sourceFrameStart,
}) =>
    _wal(
      timerStart: timerStart,
      seconds: seconds,
      clockRun: clockRun,
      recordingSessionId: recordingSessionId,
      captureRoot: captureRoot,
      sourceClockEpoch: sourceClockEpoch,
      sourceFrameStart: sourceFrameStart,
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
  late Set<String> refuseNames;
  Object? refuseWith;

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
    refuseNames = {};
    refuseWith = null;
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
          final names = files.map((file) => file.uri.pathSegments.last).toList();
          uploadAttempts.add(names);
          if (refuseWith != null) throw refuseWith!;
          if (names.any(refuseNames.contains)) {
            throw const SyncInvalidCaptureTimeException(serverReason: 'invalid timestamp');
          }
          return UploadFilesResult.queued('job-${uploadAttempts.length}');
        },
        fairUseStatusLoader: () async => {'stage': 'none'},
      ),
      persistWals: (wals) async => WalFileManager.saveWals(wals),
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
    refuseNames.add(wal.filePath!);

    await sync.syncAll();

    expect(wal.status, WalStatus.uploadRejected, reason: 'the refusal parks the row, never the audio');
    expect(wal.uploadRejectionReason, WalUploadRejection.invalidCaptureTime);
    expect(await sync.getAllWals(), hasLength(1), reason: 'the row stays for the user to delete');
    expect(file.existsSync(), isTrue, reason: 'an invalid_capture_time refusal never deletes audio');
    expect(
        uploadAttempts,
        [
          [wal.filePath!]
        ],
        reason: 'a refused row is never re-offered automatically');
    final reloaded = await WalFileManager.loadWals();
    expect(reloaded.single.uploadRejectionReason, WalUploadRejection.invalidCaptureTime,
        reason: 'the reason survives a restart');
  });

  test('a refused recording keeps its own time and file even beside contiguous audio', () async {
    // The exact shape that used to be re-dated: a predecessor frame-adjacent
    // on the source's own clock, sharing the clock run, ending exactly where
    // this chunk begins. No date is derived from it any more — the file's own
    // name is the only honest witness of when it claims to have been recorded.
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final predecessor = _neighbour(
      timerStart: now - 3600,
      seconds: 120,
      clockRun: 'run1',
      captureRoot: 'root1',
      sourceClockEpoch: 7,
      sourceFrameStart: 50000 - 12000,
    );
    final wal = _wal(
      timerStart: now - 3600 + 120,
      seconds: 60,
      clockRun: 'run1',
      captureRoot: 'root1',
      sourceClockEpoch: 7,
      sourceFrameStart: 50000,
    );
    final file = await writeAudio(wal);
    await writeAudio(predecessor);
    sync.testWals = [wal, predecessor];
    refuseNames.add(wal.filePath!);

    await sync.syncAll();

    expect(wal.status, WalStatus.uploadRejected);
    expect(wal.uploadRejectionReason, WalUploadRejection.invalidCaptureTime);
    expect(wal.timerStart, now - 3600 + 120, reason: 'no date is invented, not even a proven contiguous one');
    expect(wal.filePath, file.uri.pathSegments.last, reason: 'the file keeps its own name');
    expect(wal.clockRun, 'run1', reason: 'nothing is re-stamped onto the row');
    expect(file.existsSync(), isTrue);
    expect(
      tempDir.listSync().where((e) => e.path.endsWith('.bin')),
      hasLength(2),
      reason: 'no copy is left beside the originals',
    );
    expect(
        uploadAttempts,
        [
          [wal.filePath!]
        ],
        reason: 'nothing is re-offered under a new name');
  });

  test('a batch refusal is isolated so only the refused file is marked, never its batch-mates', () async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final offender = _wal(timerStart: now - 600, seconds: 60);
    final healthy = _wal(timerStart: now - 300, seconds: 60);
    await writeAudio(offender);
    await writeAudio(healthy);
    sync.testWals = [offender, healthy];
    refuseNames.add(offender.filePath!);

    await sync.syncAll();

    // The request-level refusal names nobody, so the batch is isolated and
    // each file tried once on its own before any verdict is kept.
    expect(uploadAttempts.first, containsAll([offender.filePath, healthy.filePath]),
        reason: 'fixture: the two recordings leave in one batch');
    expect(offender.status, WalStatus.uploadRejected);
    expect(offender.uploadRejectionReason, WalUploadRejection.invalidCaptureTime);
    expect(healthy.status, WalStatus.uploaded, reason: 'a batch-mate the refusal did not name keeps its chance');
    expect(File('${tempDir.path}/${offender.filePath}').existsSync(), isTrue);
    expect(uploadAttempts, hasLength(3), reason: 'the batch, then each member once on its own');
  });

  test('a manual retry resends the refused file unchanged', () async {
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final wal = _wal(timerStart: now - 600, seconds: 60);
    final file = await writeAudio(wal);
    sync.testWals = [wal];
    refuseNames.add(wal.filePath!);
    await sync.syncAll();
    expect(wal.status, WalStatus.uploadRejected);

    // The server's clock window widens (server PR #23746): the same bytes now pass.
    refuseNames.clear();
    await sync.syncWal(wal: wal);

    expect(
        uploadAttempts,
        [
          [wal.filePath!],
          [wal.filePath!]
        ],
        reason: 'the retry resends the same file under the same name');
    expect(wal.status, WalStatus.uploaded);
    expect(wal.timerStart, now - 600, reason: 'the recording keeps the time it claims');
    expect(wal.filePath, file.uri.pathSegments.last);
  });

  test('other 400s stay terminal and keep the server-side classification', () async {
    final wal = _wal(timerStart: 1800000000, seconds: 60);
    await writeAudio(wal);
    sync.testWals = [wal];
    refuseWith = const SyncUploadHttpException(400, 'audio malformed');

    await sync.syncAll();

    expect(wal.status, WalStatus.uploadRejected);
    expect(wal.uploadRejectionReason, WalUploadRejection.serverRefused);
    expect(uploadAttempts, hasLength(1), reason: 'no time repair happens for a non-time refusal');
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
