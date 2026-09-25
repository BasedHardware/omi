import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/bt_device/bt_device.dart';
import 'package:omi/services/capture/capture_voice_meter.dart';

Uint8List pcm(double amplitude, {int samples = 160}) {
  final data = ByteData(samples * 2);
  for (var i = 0; i < samples; i++) {
    data.setInt16(i * 2, (amplitude * math.sin(i * 0.3)).round(), Endian.little);
  }
  return data.buffer.asUint8List();
}

void main() {
  late DateTime now;
  late CaptureVoiceMeter meter;

  setUp(() {
    now = DateTime.utc(2026, 9, 25);
    meter = CaptureVoiceMeter(now: () => now);
  });

  void feed(Uint8List audio, Duration duration) {
    final end = now.add(duration);
    while (now.isBefore(end)) {
      meter.add(audio, BleAudioCodec.pcm16);
      now = now.add(const Duration(milliseconds: 10));
    }
  }

  test('silence is flat and never counts as voice', () {
    feed(pcm(0), const Duration(seconds: 2));
    expect(meter.hasSignal, true);
    expect(meter.voiceActive, false);
    expect(meter.levels().every((level) => level == 0), true);
  });

  test('speech above the room is voice and settles after the hangover', () {
    feed(pcm(60), const Duration(seconds: 3));
    expect(meter.voiceActive, false, reason: 'quiet room audio stays under the introduction screen threshold');
    feed(pcm(9000), const Duration(milliseconds: 600));
    expect(meter.voiceActive, true);
    final levels = meter.levels();
    expect(levels, hasLength(CaptureVoiceMeter.history));
    expect(levels.last, greaterThan(70));
    feed(pcm(60), const Duration(seconds: 2));
    expect(meter.voiceActive, false);
  });

  test('bins are absolute so a scrolling strip keeps identity', () {
    feed(pcm(9000), const Duration(milliseconds: 250));
    final first = meter.latestBin;
    now = now.add(const Duration(seconds: 1));
    expect(meter.latestBin, first + 1000 ~/ CaptureVoiceMeter.binMilliseconds);
  });

  test('audio stopping clears signal and voice', () {
    feed(pcm(9000), const Duration(milliseconds: 500));
    now = now.add(const Duration(seconds: 3));
    expect(meter.hasSignal, false);
    expect(meter.voiceActive, false);
    // Bins with no audio read as silence; older speech stays in history.
    expect(meter.levels().reversed.take(20).every((level) => level == 0), true);
  });

  test('unaligned PCM views are measured', () {
    feed(pcm(60), const Duration(milliseconds: 250));
    final padded = Uint8List(321)..setRange(1, 321, pcm(9000));
    meter.add(Uint8List.sublistView(padded, 1), BleAudioCodec.pcm16);
    expect(meter.voiceActive, true);
  });

  test('Opus packets decode through the injected decoder', () {
    var loud = false;
    meter = CaptureVoiceMeter(now: () => now, opusDecoder: () => (_) => pcm(loud ? 9000 : 60).buffer.asInt16List());
    for (var i = 0; i < 25; i++, now = now.add(const Duration(milliseconds: 20))) {
      meter.add([1, 2, 3], BleAudioCodec.opusFS320);
    }
    expect(meter.voiceActive, false);
    loud = true;
    meter.add([1, 2, 3], BleAudioCodec.opusFS320);
    expect(meter.voiceActive, true);
  });

  test('a failing decoder disables metering without throwing', () {
    var created = 0;
    meter = CaptureVoiceMeter(
      now: () => now,
      opusDecoder: () {
        created++;
        throw StateError('opus unavailable');
      },
    );
    meter.add([1, 2, 3], BleAudioCodec.opus);
    meter.add([1, 2, 3], BleAudioCodec.opus);
    expect(created, 1);
    expect(meter.hasSignal, false);
  });

  test('unsupported codecs are ignored and dispose runs cleanup', () {
    var disposed = false;
    meter = CaptureVoiceMeter(now: () => now, onDispose: () => disposed = true);
    meter.add([1, 2, 3, 4], BleAudioCodec.aac);
    expect(meter.hasSignal, false);
    meter.dispose();
    expect(disposed, true);
  });
}
