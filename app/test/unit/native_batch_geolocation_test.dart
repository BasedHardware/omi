import 'dart:async';
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

  test('preference fence drops a late write from the prior batch session', () async {
    final writes = <Geolocation?>[];
    final firstWriteStarted = Completer<void>();
    final releaseFirstWrite = Completer<void>();
    var call = 0;
    final fence = NativeBatchGeolocationPreferenceFence(
      writer: (geolocation) async {
        call++;
        if (call == 1) {
          firstWriteStarted.complete();
          await releaseFirstWrite.future;
        }
        writes.add(geolocation);
      },
    );
    final first = fence.beginSession();
    final firstClear = fence.writeIfCurrent(first, null);
    await firstWriteStarted.future;

    final staleLocation = Geolocation(latitude: 1, longitude: 2, time: DateTime.utc(2026));
    final staleWrite = fence.writeIfCurrent(first, staleLocation);
    final second = fence.beginSession();
    final secondClear = fence.writeIfCurrent(second, null);
    releaseFirstWrite.complete();
    await Future.wait([firstClear, staleWrite, secondClear]);

    expect(writes, [null, null]);
  });

  test('invalidating a batch session prevents a pending location publish', () async {
    final writes = <Geolocation?>[];
    final fence = NativeBatchGeolocationPreferenceFence(writer: (geolocation) async => writes.add(geolocation));
    final generation = fence.beginSession();
    fence.invalidateSession();

    await fence.writeIfCurrent(
      generation,
      Geolocation(latitude: 1, longitude: 2, time: DateTime.utc(2026)),
    );

    expect(writes, isEmpty);
  });

  test('new-session clear wins after an already-started prior publish', () async {
    final writes = <Geolocation?>[];
    final staleWriteStarted = Completer<void>();
    final releaseStaleWrite = Completer<void>();
    final staleLocation = Geolocation(latitude: 1, longitude: 2, time: DateTime.utc(2026));
    final fence = NativeBatchGeolocationPreferenceFence(
      writer: (geolocation) async {
        if (identical(geolocation, staleLocation)) {
          staleWriteStarted.complete();
          await releaseStaleWrite.future;
        }
        writes.add(geolocation);
      },
    );
    final first = fence.beginSession();
    final staleWrite = fence.writeIfCurrent(first, staleLocation);
    await staleWriteStarted.future;

    final second = fence.beginSession();
    final secondClear = fence.writeIfCurrent(second, null);
    releaseStaleWrite.complete();
    await Future.wait([staleWrite, secondClear]);

    expect(writes, [staleLocation, null]);
  });
}
