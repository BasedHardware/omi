import 'dart:typed_data';

/// Codec of a [VideoFrame] payload emitted on the
/// `meta_wearables_dat_flutter/video_frames` channel.
///
/// - [raw] is platform-defined raw planar pixel data: BGRA on iOS (with
///   row-stride encoded in [VideoFrame.bytesPerRow]) and I420
///   (Y/U/V concatenated to `width * height * 3/2`) on Android.
/// - [hvc1] is HEVC NAL bytes prefixed with VPS/SPS/PPS on each keyframe.
///   Wired by Slice G of the v0.2 implementation plan. iOS only; on
///   Android the texture path is not available for `hvc1` because
///   surfacing the compressed frame back into a preview requires a
///   `MediaCodec` decoder host apps must wire themselves.
enum VideoCodec {
  /// Uncompressed BGRA (iOS) / I420 (Android) bytes.
  raw,

  /// HEVC (`hvc1`) NAL bytes with embedded VPS/SPS/PPS on keyframes.
  hvc1,
}

/// One video frame pushed onto the `videoFramesStream`.
///
/// At 720p the raw BGRA payload is roughly 3.7 MB per frame; subscribe
/// only while you actually need every frame. When no Dart subscriber is
/// attached, the native side skips the per-frame serialisation
/// entirely (see `doc/frame_processing.md`).
class VideoFrame {
  /// Creates a [VideoFrame].
  const VideoFrame({
    required this.codec,
    required this.bytes,
    required this.width,
    required this.height,
    required this.ptsUs,
    required this.isKeyframe,
    this.bytesPerRow,
  });

  /// Codec of [bytes].
  final VideoCodec codec;

  /// Raw payload. Format depends on [codec] / platform — see [VideoCodec].
  final Uint8List bytes;

  /// Pixel width of the frame.
  final int width;

  /// Pixel height of the frame.
  final int height;

  /// Presentation timestamp in microseconds, monotonic from session start.
  final int ptsUs;

  /// True when this is a keyframe (I-frame). Always true for [VideoCodec.raw]
  /// frames; meaningful for [VideoCodec.hvc1].
  final bool isKeyframe;

  /// Row stride in bytes. Only set for iOS [VideoCodec.raw] frames (BGRA
  /// row padding may differ from `width * 4`). Always `null` for Android
  /// raw frames (I420 planes are tightly packed) and for [VideoCodec.hvc1]
  /// frames.
  final int? bytesPerRow;

  /// Reads a [VideoFrame] from the platform-channel map.
  factory VideoFrame.fromMap(Map<Object?, Object?> map) {
    final codecRaw = map['codec'];
    final codec = codecRaw == 'hvc1' ? VideoCodec.hvc1 : VideoCodec.raw;
    final bytes = map['bytes'];
    final bytesList = switch (bytes) {
      final Uint8List u => u,
      final List<int> l => Uint8List.fromList(l),
      _ => Uint8List(0),
    };
    return VideoFrame(
      codec: codec,
      bytes: bytesList,
      width: (map['width'] as int?) ?? 0,
      height: (map['height'] as int?) ?? 0,
      ptsUs: (map['ptsUs'] as int?) ?? 0,
      isKeyframe: (map['isKeyframe'] as bool?) ?? true,
      bytesPerRow: map['bytesPerRow'] as int?,
    );
  }
}
