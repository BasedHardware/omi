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
/// capture time (HTTP 400 with a bounded code), not its audio. Sub-second
/// splice wreckage disappears quietly, longer fragments are re-stamped with a
/// plausible time and re-offered once, and a second refusal is terminal with
/// the reason kept — never again a bare "Failed" row per fragment.

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
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  late Directory tempDir;
  late LocalWalSyncImpl sync;
  late List<List<String>> uploadAttempts;
  late Object? refuseWith;
  int acceptAfter = 0;

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

  test('a fragment shorter than 1.5s is discarded quietly, not parked as Failed', () async {
    // One second of audio: the kind of splice wreckage the corrupted-marker
    // split produced by the thousand.
    final wal = _wal(timerStart: 2051222400, seconds: 1); // claimed 2035
    final file = await writeAudio(wal);
    sync.testWals = [wal];
    refuseWith = const SyncInvalidCaptureTimeException(serverReason: 'invalid timestamp');
    acceptAfter = 99;

    await sync.syncAll();

    expect(await sync.getAllWals(), isEmpty, reason: 'no row may remain for a discarded fragment');
    expect(wal.status, isNot(WalStatus.uploadRejected), reason: 'a discard must never read as Failed');
    expect(file.existsSync(), isFalse, reason: 'the fragment audio is deleted with the row');
  });

  test('a longer fragment is re-stamped inside the server-accepted window and re-offered once', () async {
    final wal = _wal(timerStart: 2051222400, seconds: 60); // claimed 2035
    await writeAudio(wal);
    sync.testWals = [wal];
    refuseWith = const SyncInvalidCaptureTimeException(serverReason: 'invalid timestamp');
    acceptAfter = 1; // refused once, then accepted

    await sync.syncAll();

    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    expect(uploadAttempts, hasLength(2), reason: 'the restamped file is re-offered in the same drain');
    expect(uploadAttempts.first, isNot(uploadAttempts.last), reason: 'the re-offer carries a renamed file');
    expect(wal.status, WalStatus.uploaded, reason: 'the re-stamped upload is accepted');
    expect(wal.timerStart, greaterThanOrEqualTo(1704067200), reason: 'never before 2024-01-01');
    expect(wal.timerStart, lessThanOrEqualTo(now), reason: 'never in the future');
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

  test('estimatedCaptureStartSeconds prefers the latest neighbour that is not in the future', () {
    const now = 1790000000;
    // A plausible neighbour ending now-10 wins over an earlier one and over a
    // future neighbour end (a garbage-clock sibling must not drag the estimate).
    expect(
      estimatedCaptureStartSeconds(
        nowSeconds: now,
        neighbourSpans: const [(1704067200, 1704070000), (1789999990 - 60, 1789999990), (2051222400, 2051222460)],
      ),
      1789999990,
    );
    // No usable neighbour: the file's own timestamp stands, clamped to now.
    expect(
      estimatedCaptureStartSeconds(
          nowSeconds: now, fileTimestamp: DateTime.fromMillisecondsSinceEpoch(1790000100 * 1000)),
      now,
    );
    // Nothing usable at all: the floor the server enforces.
    expect(estimatedCaptureStartSeconds(nowSeconds: now), 1704067200);
  });

  test('syncUploadErrorCode and syncUploadErrorReason parse the bounded 400 body', () {
    http.Response body(String payload) => http.Response(payload, 400);

    expect(syncUploadErrorCode(body('{"detail": "invalid timestamp", "code": "invalid_capture_time"}')),
        'invalid_capture_time');
    expect(syncUploadErrorCode(body('{"detail": "invalid timestamp"}')), isNull);
    expect(syncUploadErrorCode(body('not json')), isNull);
    expect(syncUploadErrorReason(body('{"detail": "invalid timestamp", "code": "invalid_capture_time"}')),
        'invalid timestamp');
    expect(syncUploadErrorReason(body('{"message": "too many files"}')), 'too many files');
    expect(syncUploadErrorReason(body('not json')), isNull);
  });
}
