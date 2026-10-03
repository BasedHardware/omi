import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/voice_playback/device_speaker_pcm.dart';

void main() {
  group('DeviceSpeakerPcm.downsamplePcm16Le', () {
    test('takes every second sample from 16 kHz to 8 kHz', () {
      final src = ByteData(8);
      src.setInt16(0, 100, Endian.little);
      src.setInt16(2, 200, Endian.little);
      src.setInt16(4, 300, Endian.little);
      src.setInt16(6, 400, Endian.little);

      final out = DeviceSpeakerPcm.downsamplePcm16Le(
        pcm: src.buffer.asUint8List(),
        fromRateHz: 16000,
        toRateHz: 8000,
      );

      expect(out.length, 4);
      final view = ByteData.sublistView(out);
      expect(view.getInt16(0, Endian.little), 100);
      expect(view.getInt16(2, Endian.little), 300);
    });

    test('returns a copy when rates match', () {
      final pcm = Uint8List.fromList([1, 2, 3, 4]);
      final out = DeviceSpeakerPcm.downsamplePcm16Le(
        pcm: pcm,
        fromRateHz: 8000,
        toRateHz: 8000,
      );
      expect(out, pcm);
      expect(identical(out, pcm), isFalse);
    });
  });

  group('DeviceSpeakerPcm.ensurePlayableLength', () {
    test('pads when length is a multiple of the BLE packet size', () {
      final pcm = Uint8List(DeviceSpeakerPcm.packetSize);
      final out = DeviceSpeakerPcm.ensurePlayableLength(pcm);
      expect(out.length, DeviceSpeakerPcm.packetSize + 2);
      expect(out.length % DeviceSpeakerPcm.packetSize, isNonZero);
    });

    test('leaves non-multiples unchanged', () {
      final pcm = Uint8List(123);
      expect(identical(DeviceSpeakerPcm.ensurePlayableLength(pcm), pcm), isTrue);
    });
  });

  group('DeviceSpeakerPcm.frameForDevice', () {
    test('splits into firmware-sized frames', () {
      final pcm = Uint8List(DeviceSpeakerPcm.maxMonoBytesPerCycle * 2 + 10);
      final frames = DeviceSpeakerPcm.frameForDevice(pcm);
      expect(frames.length, 3);
      expect(frames[0].length, lessThanOrEqualTo(DeviceSpeakerPcm.maxMonoBytesPerCycle + 2));
      expect(frames[1].length, lessThanOrEqualTo(DeviceSpeakerPcm.maxMonoBytesPerCycle + 2));
      expect(frames[2].length, 10);
    });
  });

  group('DeviceSpeakerPcm.lengthHeader', () {
    test('encodes little-endian uint32', () {
      final header = DeviceSpeakerPcm.lengthHeader(0x01020304);
      expect(header, [0x04, 0x03, 0x02, 0x01]);
    });
  });
}
