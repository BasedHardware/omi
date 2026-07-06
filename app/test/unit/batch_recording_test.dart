import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/batch_recording.dart';

void main() {
  group('BatchRecordingInfo.fromFileName', () {
    test('parses opus fs160', () {
      final info = BatchRecordingInfo.fromFileName('audio_omi_opus_16000_1_fs160_1735689600.bin');
      expect(info, isNotNull);
      expect(info!.codec, BleAudioCodec.opus);
      expect(info.frameSize, 160);
      expect(info.timerStart, 1735689600);
    });

    test('parses opus_fs320 (frame size disambiguates the codec)', () {
      final info = BatchRecordingInfo.fromFileName('audio_omi_opus_fs320_16000_1_fs320_1735689600.bin');
      expect(info, isNotNull);
      expect(info!.codec, BleAudioCodec.opusFS320);
      expect(info.frameSize, 320);
      expect(info.timerStart, 1735689600);
    });

    test('parses the limitless flash-drain marker (omibatchlimitless)', () {
      final info = BatchRecordingInfo.fromFileName(
          'audio_${limitlessBatchRecordingDevice}_opus_fs320_16000_1_fs320_1735689600.bin');
      expect(info, isNotNull);
      expect(info!.codec, BleAudioCodec.opusFS320);
      expect(info.frameSize, 320);
      expect(info.sampleRate, 16000);
      expect(info.timerStart, 1735689600);
      expect('audio_${limitlessBatchRecordingDevice}_'.startsWith('audio_$batchRecordingDevice'), isTrue);
    });

    test('parses pcm16', () {
      final info = BatchRecordingInfo.fromFileName('audio_omi_pcm16_16000_1_fs160_1735689600.bin');
      expect(info!.codec, BleAudioCodec.pcm16);
    });

    test('parses pcm8', () {
      final info = BatchRecordingInfo.fromFileName('audio_omi_pcm8_8000_1_fs160_1735689600.bin');
      expect(info!.codec, BleAudioCodec.pcm8);
    });

    test('normalizes millisecond timestamps to seconds', () {
      final info = BatchRecordingInfo.fromFileName('audio_omi_opus_16000_1_fs160_1735689600000.bin');
      expect(info!.timerStart, 1735689600);
    });

    test('rejects non-batch / in-progress / malformed files', () {
      expect(BatchRecordingInfo.fromFileName('wals.json'), isNull);
      // .bin.part is the in-progress file — must not be ingested
      expect(BatchRecordingInfo.fromFileName('audio_omi_opus_16000_1_fs160_1735689600.bin.part'), isNull);
      expect(BatchRecordingInfo.fromFileName('audio_omi_opus_16000_1_fs160_notanumber.bin'), isNull);
      expect(BatchRecordingInfo.fromFileName('random_file.bin'), isNull);
    });

    test('round-trips with Wal.getFileName', () {
      final wal = Wal(timerStart: 1735689600, codec: BleAudioCodec.opus, seconds: 60, device: 'omi');
      final info = BatchRecordingInfo.fromFileName(wal.getFileName());
      expect(info, isNotNull);
      expect(info!.codec, BleAudioCodec.opus);
      expect(info.timerStart, 1735689600);
      expect(info.frameSize, wal.frameSize);
    });

    test('estimateSeconds is bounded and codec-aware', () {
      final opus = BatchRecordingInfo.fromFileName('audio_omi_opus_16000_1_fs160_1735689600.bin')!;
      // ~2400 B/s for opus -> 240000 bytes ~= 100s
      expect(opus.estimateSeconds(240000), inInclusiveRange(90, 110));
      expect(opus.estimateSeconds(0), 1); // clamped to >= 1
    });

    test('parses sample rate', () {
      expect(BatchRecordingInfo.fromFileName('audio_omi_opus_16000_1_fs160_1735689600.bin')!.sampleRate, 16000);
      expect(BatchRecordingInfo.fromFileName('audio_omi_pcm8_8000_1_fs160_1735689600.bin')!.sampleRate, 8000);
    });
  });

  group('BatchRecordingInfo.secondsFromFrameCount', () {
    test('exact duration is frames * frameSize / sampleRate (opus fs160 = 10ms/frame)', () {
      final info = BatchRecordingInfo.fromFileName('audio_omibatch_opus_16000_1_fs160_1735689600.bin')!;
      // A 15-min file capped at 900s of continuous 10ms frames = 90000 frames.
      expect(info.secondsFromFrameCount(90000), 900);
      expect(info.secondsFromFrameCount(6000), 60);
    });

    test('fs320 frames are 20ms each', () {
      final info = BatchRecordingInfo.fromFileName('audio_omibatch_opus_fs320_16000_1_fs320_1735689600.bin')!;
      expect(info.secondsFromFrameCount(45000), 900);
    });

    test('is bounded to >= 1 second', () {
      final info = BatchRecordingInfo.fromFileName('audio_omibatch_opus_16000_1_fs160_1735689600.bin')!;
      expect(info.secondsFromFrameCount(0), 1);
    });
  });
}
