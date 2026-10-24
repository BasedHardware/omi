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

  group('canAutoUploadPhoneRecordings', () {
    test('returns true when allowed', () {
      expect(
        canAutoUploadPhoneRecordings(
          useCustomStt: false,
          autoSyncOfflineRecordings: true,
          isUploading: false,
        ),
        isTrue,
      );
    });

    test('returns false when custom STT is used', () {
      expect(
        canAutoUploadPhoneRecordings(
          useCustomStt: true,
          autoSyncOfflineRecordings: true,
          isUploading: false,
        ),
        isFalse,
      );
    });

    test('returns false when auto sync is disabled', () {
      expect(
        canAutoUploadPhoneRecordings(
          useCustomStt: false,
          autoSyncOfflineRecordings: false,
          isUploading: false,
        ),
        isFalse,
      );
    });

    test('returns false when already uploading', () {
      expect(
        canAutoUploadPhoneRecordings(
          useCustomStt: false,
          autoSyncOfflineRecordings: true,
          isUploading: true,
        ),
        isFalse,
      );
    });
  });

  group('selectNextAutoPhoneUpload', () {
    const explicit = 'audio_omibatchphone_opus_fs320_16000_1_fs320_1720000000.bin';
    const auto1 = 'audio_omibatchphoneauto_opus_fs320_16000_1_fs320_1720000001.bin';
    const auto2 = 'audio_omibatchphoneauto_opus_fs320_16000_1_fs320_1720000002.bin';
    const other = 'audio_omi_opus_16000_1_fs160_1720000000.bin';

    test('returns null if no files provided', () {
      expect(
        selectNextAutoPhoneUpload([], busyNames: {}, failureCounts: {}),
        isNull,
      );
    });

    test('skips explicit and other files, returns first valid auto file', () {
      expect(
        selectNextAutoPhoneUpload([explicit, other, auto1, auto2], busyNames: {}, failureCounts: {}),
        auto1,
      );
    });

    test('skips busy files', () {
      expect(
        selectNextAutoPhoneUpload([auto1, auto2], busyNames: {auto1}, failureCounts: {}),
        auto2,
      );

      expect(
        selectNextAutoPhoneUpload([auto1], busyNames: {auto1}, failureCounts: {}),
        isNull,
      );
    });

    test('skips files with failure count >= max failures', () {
      expect(
        selectNextAutoPhoneUpload([auto1, auto2], busyNames: {}, failureCounts: {auto1: 3}),
        auto2,
      );

      expect(
        selectNextAutoPhoneUpload([auto1], busyNames: {}, failureCounts: {auto1: 3}),
        isNull,
      );
    });

    test('does not skip files with failure count < max failures', () {
      expect(
        selectNextAutoPhoneUpload([auto1, auto2], busyNames: {}, failureCounts: {auto1: 2}),
        auto1,
      );
    });
  });
}
