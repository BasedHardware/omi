import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/sockets/listen_client_state.dart';
import 'package:omi/services/wals/mobile_batch_buffer.dart';
import 'package:omi/services/wals/mobile_batch_vad.dart';
import 'package:omi/services/wals/mobile_standard_batch.dart';
import 'package:omi/services/wals/wal.dart';
import 'package:omi/utils/reliability_experiments.dart';

// Reliability experiment vendor_recognizer_on_opened_app, step 4: opening a transcript page seals the
// phone file being written in a local-preview session too, so the stored text behind the live words
// arrives sooner. Off, a local-preview session leaves the open file to its own rules, as before.

class _Vad implements MobileBatchVad {
  @override
  Future<double> probability(List<int> opus) async => 0.4;
  @override
  Future<void> close() async {}
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();
  late Directory directory;
  late MobileBatchBuffer buffer;
  late MobileStandardBatch lane;
  late List<Wal> published;
  final state = ListenClientState.instance;
  final clock = DateTime.utc(2026, 11, 25);

  setUp(() async {
    directory = await Directory.systemTemp.createTemp('live_words_seal_');
    published = [];
    buffer = MobileBatchBuffer(directory: directory, publish: (wal) async => published.add(wal));
    state.resetForTest();
    lane = MobileStandardBatch(
        buffer: buffer,
        loadVad: () async => _Vad(),
        freeDiskBytes: () async => 1 << 40,
        visibility: state,
        ownerUid: () => 'owner',
        now: () => clock);
  });
  tearDown(() async {
    ReliabilityExperiments.overrideForTesting(null);
    await lane.close();
    state.resetForTest();
    await directory.delete(recursive: true);
  });

  Future<void> speakIntoALocalPreviewSession() async {
    lane.authorize(true, localPreview: true);
    await lane.pendingInitialization;
    for (var i = 0; i < 5; i++) {
      expect(lane.route([1], codec: BleAudioCodec.opus, realtimeConsumer: false), true);
    }
    await lane.pendingInference;
    await buffer.pending;
    expect(published, isEmpty, reason: 'still speaking: the phone file stays open');
  }

  test('off: opening the transcript page leaves a local-preview session\'s open phone file alone', () async {
    await speakIntoALocalPreviewSession();
    state.capturePageOpened();
    lane.visibilityChanged();
    await buffer.pending;
    expect(published, isEmpty);
  });

  test('on: opening the transcript page seals it, and later audio opens the next phone file', () async {
    ReliabilityExperiments.overrideForTesting({'vendor_recognizer_on_opened_app'});
    await speakIntoALocalPreviewSession();
    state.capturePageOpened();
    lane.visibilityChanged();
    await buffer.pending;
    expect(published, hasLength(1));
    expect(published.single.totalFrames, 5);
    // Still a local-preview session: audio keeps going to phone files while the page is open.
    expect(lane.route([2], codec: BleAudioCodec.opus, realtimeConsumer: false), true);
    // Closing the page seals nothing more by itself.
    state.capturePageClosed();
    lane.visibilityChanged();
    await buffer.pending;
    expect(published, hasLength(1));
  });
}
