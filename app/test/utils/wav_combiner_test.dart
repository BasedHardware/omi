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

class _BrokenStreamFile extends Fake implements File {
  final File source;
  _BrokenStreamFile(this.source);
  @override
  String get path => source.path;
  @override
  Future<Uint8List> readAsBytes() => source.readAsBytes();
  @override
  Future<RandomAccessFile> open({FileMode mode = FileMode.read}) => source.open(mode: mode);
  @override
  Stream<List<int>> openRead([int? start, int? end]) async* {
    yield [1, 2];
    throw const FileSystemException('Synthetic read failure');
  }
}

void main() {
  late Directory dir;

  setUp(() async {
    dir = await Directory.systemTemp.createTemp('wav_combiner_test');
  });

  tearDown(() async {
    if (await dir.exists()) await dir.delete(recursive: true);
  });

  File write(String name, List<int> bytes) => File('${dir.path}/$name')..writeAsBytesSync(bytes);

  test('combines valid WAV parts', () async {
    final a = write('a.wav', _wav(100));
    final b = write('b.wav', _wav(60));

    final out = await WavCombiner.combineWavFiles([a, b], '${dir.path}/out.wav');
    final bytes = await out.readAsBytes();

    expect(String.fromCharCodes(bytes.sublist(0, 4)), 'RIFF');
    expect(bytes.length, 44 + 100 + 60);
  });

  test('skips a corrupt part (missing RIFF) and combines the rest', () async {
    final a = write('a.wav', _wav(100));
    final bad = write('bad.wav', List.filled(200, 7)); // no RIFF header
    final c = write('c.wav', _wav(60));

    final out = await WavCombiner.combineWavFiles([a, bad, c], '${dir.path}/out.wav');
    final bytes = await out.readAsBytes();

    expect(String.fromCharCodes(bytes.sublist(0, 4)), 'RIFF');
    expect(bytes.length, 44 + 100 + 60);
  });

  test('one valid part among corrupt parts is returned as-is', () async {
    final bad = write('bad.wav', List.filled(200, 7));
    final tooSmall = write('small.wav', List.filled(10, 3));
    final good = write('good.wav', _wav(80));

    final out = await WavCombiner.combineWavFiles([bad, good, tooSmall], '${dir.path}/out.wav');
    final bytes = await out.readAsBytes();

    expect(bytes.length, 44 + 80);
  });

  test('stream failure preserves previous export and removes partial output', () async {
    final a = write('a.wav', _wav(4));
    final b = _BrokenStreamFile(write('b.wav', _wav(4)));
    final out = write('out.wav', [42]);
    final before = (await dir.list().map((e) => e.path).toList()).toSet();
    await expectLater(WavCombiner.combineWavFiles([a, b], out.path), throwsA(isA<FileSystemException>()));
    expect(await out.readAsBytes(), [42]);
    expect((await dir.list().map((e) => e.path).toList()).toSet(), before);
  });

  test('truncated payload is skipped without corrupting the final duration', () async {
    final bad = write('truncated.wav', _wav(100).sublist(0, 46));
    final good = write('good.wav', _wav(8));
    final out = await WavCombiner.combineWavFiles([bad, good], '${dir.path}/out.wav');
    expect(await out.readAsBytes(), _wav(8));
  });

  test('throws when no part is a valid WAV', () async {
    final bad1 = write('b1.wav', List.filled(200, 7));
    final bad2 = write('b2.wav', List.filled(10, 3));

    expect(
      () => WavCombiner.combineWavFiles([bad1, bad2], '${dir.path}/out.wav'),
      throwsException,
    );
  });
}
