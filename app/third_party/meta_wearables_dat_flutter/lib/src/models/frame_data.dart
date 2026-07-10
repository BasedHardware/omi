import 'dart:typed_data';

/// A single frame snapshot returned by [MetaWearablesDat.captureStreamFrame].
///
/// Frames are produced on demand from Flutter's texture registry, not pushed
/// every video frame. At 720x1280 the raw RGBA payload is roughly 3.7 MB;
/// budget your sampling rate accordingly (200-500 ms is a good starting point
/// for OCR / ML pipelines).
class FrameData {
  /// Creates a [FrameData].
  const FrameData({
    required this.bytes,
    required this.width,
    required this.height,
    required this.format,
  });

  /// Raw pixel bytes.
  final Uint8List bytes;

  /// Pixel width.
  final int width;

  /// Pixel height.
  final int height;

  /// Pixel format of [bytes].
  final FrameFormat format;
}

/// Pixel format of a [FrameData] payload.
enum FrameFormat {
  /// 32-bit per pixel, RGBA (red, green, blue, alpha) with **premultiplied
  /// alpha**. This is what `ui.Image.toByteData()` returns by default.
  rawRgba,

  /// 32-bit per pixel, RGBA with **straight (un-premultiplied) alpha**.
  rawStraightRgba,

  /// PNG-encoded bytes.
  png,

  /// JPEG-encoded bytes.
  jpeg,
}
