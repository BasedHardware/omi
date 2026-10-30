import 'dart:typed_data';

/// The existing WAL layout: one little-endian uint32 length followed by the
/// payload for each frame. Allocate the output once, without per-frame headers,
/// byte buffers, or a growable List<int> holding every output byte as an int.
Uint8List encodeWalFrames(List<List<int>> frames) {
  final length = frames.fold<int>(0, (length, frame) => length + 4 + frame.length);
  final bytes = Uint8List(length);
  final header = ByteData.sublistView(bytes);
  var offset = 0;
  for (final frame in frames) {
    header.setUint32(offset, frame.length, Endian.little);
    offset += 4;
    bytes.setRange(offset, offset + frame.length, frame);
    offset += frame.length;
  }
  return bytes;
}

/// Unchanged serializer for non-pendant WALs. Keeping this path separate leaves
/// phone and batch allocation behavior intact while optimizing the live pendant.
List<int> encodeLegacyWalFrames(List<List<int>> frames) {
  final data = <int>[];
  for (final frame in frames) {
    final byteFrame = ByteData(frame.length);
    for (var j = 0; j < frame.length; j++) {
      byteFrame.setUint8(j, frame[j]);
    }
    data.addAll(Uint32List.fromList([frame.length]).buffer.asUint8List());
    data.addAll(byteFrame.buffer.asUint8List());
  }
  return data;
}
