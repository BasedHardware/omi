import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/utils/batch_recording.dart';

/// Phone-mic × Transcribe Later: filename parsing, the auto/explicit marker
/// truth table, the scanner-prefix property both markers must satisfy, and the
/// exact duration math. Pure — no singletons, hermetic under `bash test.sh`.
void main() {
  const explicit = 'audio_omibatchphone_opus_fs320_16000_1_fs320_1720000000.bin';
  const auto = 'audio_omibatchphoneauto_opus_fs320_16000_1_fs320_1720000000.bin';

  group('BatchRecordingInfo.fromFileName — phone-mic recordings', () {
    test(
      'parses the explicit Transcribe Later phone recording (opus fs320)',
      () {
        final info = BatchRecordingInfo.fromFileName(explicit);
        expect(info, isNotNull);
        expect(info!.codec, BleAudioCodec.opusFS320);
        expect(info.frameSize, 320);
        expect(info.sampleRate, 16000);
        expect(info.timerStart, 1720000000);
      },
    );

    test(
      'parses the automatic offline-fallback phone recording identically',
      () {
        final info = BatchRecordingInfo.fromFileName(auto);
        expect(info, isNotNull);
        expect(info!.codec, BleAudioCodec.opusFS320);
        expect(info.frameSize, 320);
        expect(info.sampleRate, 16000);
        expect(info.timerStart, 1720000000);
      },
    );

    test('exact duration: 3000 fs320 frames -> 60s (3000 * 320 / 16000)', () {
      final info = BatchRecordingInfo.fromFileName(explicit)!;
      expect(info.secondsFromFrameCount(3000), 60);
      // Same math for the auto variant — codec/frameSize/sampleRate all match.
      expect(
        BatchRecordingInfo.fromFileName(auto)!.secondsFromFrameCount(3000),
        60,
      );
    });
  });

  group('marker constants', () {
    test('auto marker starts with the explicit phone marker', () {
      expect(
        phoneBatchAutoRecordingDevice.startsWith(phoneBatchRecordingDevice),
        isTrue,
      );
    });

    test('both phone markers start with the shared batch marker', () {
      expect(
        phoneBatchRecordingDevice.startsWith(batchRecordingDevice),
        isTrue,
      );
      expect(
        phoneBatchAutoRecordingDevice.startsWith(batchRecordingDevice),
        isTrue,
      );
    });

    test(
      'scanner-prefix property: both filenames match the recordings scanner (audio_omibatch*)',
      () {
        // The provider scans files whose name starts with `audio_$batchRecordingDevice`.
        expect(explicit.startsWith('audio_$batchRecordingDevice'), isTrue);
        expect(auto.startsWith('audio_$batchRecordingDevice'), isTrue);
      },
    );
  });
}
