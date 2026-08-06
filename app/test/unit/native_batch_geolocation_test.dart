import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/geolocation.dart';
import 'package:omi/models/local_recording.dart';
import 'package:omi/providers/local_recordings_provider.dart';
import 'package:omi/services/capture/native_batch_geolocation.dart';
import 'package:omi/services/wals/sync_rate_limiter.dart';
import 'package:omi/services/wals/sync_upload_gate.dart';

void main() {
  late Directory directory;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    SyncRateLimiter.instance.clear();
    directory = await Directory.systemTemp.createTemp('omi-native-batch-location-');
  });

  tearDown(() async {
    if (await directory.exists()) await directory.delete(recursive: true);
  });

  for (final marker in ['omibatchphone', 'omibatchphoneauto']) {
    test('$marker sidecar survives discovery and reaches SyncUploadGate', () async {
      final file = File('${directory.path}/audio_${marker}_opus_fs320_16000_1_fs320_1720000000.bin');
      await file.writeAsBytes([1]);
      await File(nativeBatchGeolocationSidecarPath(file.path)).writeAsString(
        jsonEncode({
          'latitude': 37.7749,
          'longitude': -122.4194,
          'accuracy': 8.0,
          'captured_at': '2026-08-01T12:30:00.000Z',
          'capture_source': 'current_position',
        }),
      );

      final snapshot = await readNativeBatchGeolocation(file.path);
      final recording = LocalRecording.fromFile(
        fileName: file.path.split('/').last,
        filePath: file.path,
        sizeBytes: 1,
        seconds: 1,
        state: LocalRecordingState.pending,
        geolocation: snapshot,
      )!;
      Geolocation? uploaded;
      final gate = SyncUploadGate(
        limiter: SyncRateLimiter.instance,
        fairUseStatusLoader: () async => {'stage': 'none'},
        uploader: (files, {onUploadProgress, conversationId, claimLiveCapture = false, geolocation}) async {
          uploaded = geolocation;
          return UploadFilesResult.queued('job-1');
        },
      );

      await uploadNativeBatchRecording(recording, file: file, uploadGate: gate);

      expect(uploaded?.latitude, 37.7749);
      expect(uploaded?.longitude, -122.4194);
      expect(uploaded?.captureSource, 'current_position');
      expect(uploaded?.time, DateTime.utc(2026, 8, 1, 12, 30));
    });
  }

  test('missing, malformed, and oversized sidecars fail soft', () async {
    final file = File('${directory.path}/audio_omibatchphone_opus_fs320_16000_1_fs320_1.bin');
    await file.writeAsBytes([1]);

    expect(await readNativeBatchGeolocation(file.path), isNull);

    final sidecar = File(nativeBatchGeolocationSidecarPath(file.path));
    await sidecar.writeAsString('{not-json');
    expect(await readNativeBatchGeolocation(file.path), isNull);

    await sidecar.writeAsString('x' * (nativeBatchGeolocationMaxBytes + 1));
    expect(await readNativeBatchGeolocation(file.path), isNull);
  });
}
