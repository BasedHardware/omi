import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/wals.dart';
import 'package:omi/utils/batch_recording.dart';
import 'package:omi/utils/wal_sync_upload.dart';

void main() {
  group('isFramedWalSyncFileName', () {
    test('accepts opus and PCM framed WAL bins', () {
      expect(isFramedWalSyncFileName('audio_omi_opus_16000_1_fs160_1735689600.bin'), isTrue);
      expect(isFramedWalSyncFileName('audio_omi_opus_fs320_16000_1_fs320_1735689600.bin'), isTrue);
      expect(isFramedWalSyncFileName('audio_omi_pcm16_16000_1_fs160_1735689600.bin'), isTrue);
      expect(isFramedWalSyncFileName('/tmp/audio_omibatch_opus_16000_1_fs160_1735689600.bin'), isTrue);
    });

    test('rejects decoded WAV and unrelated names', () {
      expect(isFramedWalSyncFileName('audio_omi_opus_16000_1_fs160_1735689600.wav'), isFalse);
      expect(isFramedWalSyncFileName('speaker_profile.wav'), isFalse);
      expect(isFramedWalSyncFileName('wals.json'), isFalse);
      expect(isFramedWalSyncFileName('audio_omi_opus_16000_1_fs160_1735689600.bin.part'), isFalse);
    });
  });

  test('Wal.getFileName is a framed bin, never wav', () {
    final wal = Wal(
      timerStart: 1735689600,
      codec: BleAudioCodec.opus,
      seconds: 60,
      sampleRate: 16000,
      device: 'omi',
    );
    final name = wal.getFileName();
    expect(name.endsWith('.bin'), isTrue);
    expect(name.contains('.wav'), isFalse);
    expect(name.contains('_opus_'), isTrue);
    expect(isFramedWalSyncFileName(name), isTrue);
    expect(BatchRecordingInfo.fromFileName(name)!.codec, BleAudioCodec.opus);
  });

  test('assertWalSyncFilesAreFramedBins throws on wav', () {
    expect(
      () => assertWalSyncFilesAreFramedBins(['audio_omi_opus_16000_1_fs160_1735689600.wav']),
      throwsArgumentError,
    );
    expect(
      () => assertWalSyncFilesAreFramedBins(['audio_omi_opus_16000_1_fs160_1735689600.bin']),
      returnsNormally,
    );
  });
}
