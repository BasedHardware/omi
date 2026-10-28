import 'dart:typed_data';

/// The fixed PCM WAV layout used by WAL playback and recording exports.
Uint8List pcmWavHeader({
  required int sampleRate,
  required int channels,
  required int bitsPerSample,
  required int dataSize,
}) {
  if (dataSize < 0 || dataSize > 0xffffffff - 36) {
    throw const FormatException('Audio exceeds the WAV size limit');
  }
  final align = channels * ((bitsPerSample + 7) ~/ 8);
  final header = ByteData(44);
  final bytes = header.buffer.asUint8List();
  bytes.setAll(0, 'RIFF'.codeUnits);
  bytes.setAll(8, 'WAVEfmt '.codeUnits);
  bytes.setAll(36, 'data'.codeUnits);
  header.setUint32(4, 36 + dataSize, Endian.little);
  header.setUint32(16, 16, Endian.little);
  header.setUint16(20, 1, Endian.little);
  header.setUint16(22, channels, Endian.little);
  header.setUint32(24, sampleRate, Endian.little);
  header.setUint32(28, sampleRate * align, Endian.little);
  header.setUint16(32, align, Endian.little);
  header.setUint16(34, bitsPerSample, Endian.little);
  header.setUint32(40, dataSize, Endian.little);
  return bytes;
}
