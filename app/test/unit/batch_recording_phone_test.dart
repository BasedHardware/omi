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
    test('parses the explicit Transcribe Later phone recording (opus fs320)', () {
      final info = BatchRecordingInfo.fromFileName(explicit);
      expect(info, isNotNull);
      expect(info!.codec, BleAudioCodec.opusFS320);
      expect(info.frameSize, 320);
      expect(info.sampleRate, 16000);
      expect(info.timerStart, 1720000000);
    });

    test('parses the automatic offline-fallback phone recording identically', () {
      final info = BatchRecordingInfo.fromFileName(auto);
      expect(info, isNotNull);
      expect(info!.codec, BleAudioCodec.opusFS320);
      expect(info.frameSize, 320);
      expect(info.sampleRate, 16000);
      expect(info.timerStart, 1720000000);
    });

    test('exact duration: 3000 fs320 frames -> 60s (3000 * 320 / 16000)', () {
      final info = BatchRecordingInfo.fromFileName(explicit)!;
      expect(info.secondsFromFrameCount(3000), 60);
      // Same math for the auto variant — codec/frameSize/sampleRate all match.
      expect(BatchRecordingInfo.fromFileName(auto)!.secondsFromFrameCount(3000), 60);
    });
  });

  group('marker constants', () {
    test('auto marker starts with the explicit phone marker', () {
      expect(phoneBatchAutoRecordingDevice.startsWith(phoneBatchRecordingDevice), isTrue);
    });

    test('both phone markers start with the shared batch marker', () {
      expect(phoneBatchRecordingDevice.startsWith(batchRecordingDevice), isTrue);
      expect(phoneBatchAutoRecordingDevice.startsWith(batchRecordingDevice), isTrue);
    });

    test('scanner-prefix property: both filenames match the recordings scanner (audio_omibatch*)', () {
      // The provider scans files whose name starts with `audio_$batchRecordingDevice`.
      expect(explicit.startsWith('audio_$batchRecordingDevice'), isTrue);
      expect(auto.startsWith('audio_$batchRecordingDevice'), isTrue);
    });
  });

  group('isAutoPhoneBatchRecording — truth table', () {
    test('true only for the auto-fallback phone marker', () {
      expect(isAutoPhoneBatchRecording(auto), isTrue);
    });

    test('false for the explicit Transcribe Later phone recording', () {
      // `audio_omibatchphoneauto_` must NOT be matched by the explicit prefix and
      // vice-versa — the explicit file stays strictly manual.
      expect(isAutoPhoneBatchRecording(explicit), isFalse);
      expect(explicit.startsWith('audio_${phoneBatchAutoRecordingDevice}_'), isFalse);
    });

    test('false for limitless, plain-omi batch, and unrelated files', () {
      expect(isAutoPhoneBatchRecording('audio_omibatchlimitless_opus_fs320_16000_1_fs320_1720000000.bin'), isFalse);
      expect(isAutoPhoneBatchRecording('audio_omibatch_opus_16000_1_fs160_1720000000.bin'), isFalse);
      expect(isAutoPhoneBatchRecording('audio_omi_opus_16000_1_fs160_1720000000.bin'), isFalse);
      expect(isAutoPhoneBatchRecording('wals.json'), isFalse);
      // A prefix without the trailing underscore must not match (guards a name
      // like `audio_omibatchphoneautofoo` from being treated as a real recording).
      expect(isAutoPhoneBatchRecording('audio_omibatchphoneauto'), isFalse);
    });
  });
}
