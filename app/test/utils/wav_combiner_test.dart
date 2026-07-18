import 'dart:io';
import 'dart:typed_data';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/audio/wav_combiner.dart';

Uint8List _wav(int dataBytes, {int sampleRate = 16000, int channels = 1, int bits = 16}) {
  final byteRate = sampleRate * channels * (bits ~/ 8);
  final blockAlign = channels * (bits ~/ 8);
  final b = BytesBuilder();
  void str(String s) => b.add(s.codeUnits);
  void u32(int v) => b.add((ByteData(4)..setUint32(0, v, Endian.little)).buffer.asUint8List());
  void u16(int v) => b.add((ByteData(2)..setUint16(0, v, Endian.little)).buffer.asUint8List());

  str('RIFF');
  u32(36 + dataBytes);
  str('WAVE');
  str('fmt ');
  u32(16);
  u16(1);
  u16(channels);
  u32(sampleRate);
  u32(byteRate);
  u16(blockAlign);
  u16(bits);
  str('data');
  u32(dataBytes);
  b.add(List.filled(dataBytes, 1));
  return b.toBytes();
}

void main() {
  late Directory dir;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('wav_combiner_test');
  });

  tearDown(() async {
    if (await dir.exists()) await dir.delete(recursive: true);
  });

  File _write(String name, List<int> bytes) => File('${dir.path}/$name')..writeAsBytesSync(bytes);

  test('combines valid WAV parts', () async {
    final a = _write('a.wav', _wav(100));
    final b = _write('b.wav', _wav(60));

    final out = await WavCombiner.combineWavFiles([a, b], '${dir.path}/out.wav');
    final bytes = await out.readAsBytes();

    expect(String.fromCharCodes(bytes.sublist(0, 4)), 'RIFF');
    expect(bytes.length, 44 + 100 + 60);
  });

  test('skips a corrupt part (missing RIFF) and combines the rest', () async {
    final a = _write('a.wav', _wav(100));
    final bad = _write('bad.wav', List.filled(200, 7)); // no RIFF header
    final c = _write('c.wav', _wav(60));

    final out = await WavCombiner.combineWavFiles([a, bad, c], '${dir.path}/out.wav');
    final bytes = await out.readAsBytes();

    expect(String.fromCharCodes(bytes.sublist(0, 4)), 'RIFF');
    expect(bytes.length, 44 + 100 + 60);
  });

  test('one valid part among corrupt parts is returned as-is', () async {
    final bad = _write('bad.wav', List.filled(200, 7));
    final tooSmall = _write('small.wav', List.filled(10, 3));
    final good = _write('good.wav', _wav(80));

    final out = await WavCombiner.combineWavFiles([bad, good, tooSmall], '${dir.path}/out.wav');
    final bytes = await out.readAsBytes();

    expect(bytes.length, 44 + 80);
  });

  test('throws when no part is a valid WAV', () async {
    final bad1 = _write('b1.wav', List.filled(200, 7));
    final bad2 = _write('b2.wav', List.filled(10, 3));

    expect(() => WavCombiner.combineWavFiles([bad1, bad2], '${dir.path}/out.wav'), throwsException);
  });
}
