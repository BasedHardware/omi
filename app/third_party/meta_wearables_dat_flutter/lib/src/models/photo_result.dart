import 'dart:typed_data';

/// A high-resolution still captured by [MetaWearablesDat.capturePhoto].
class PhotoResult {
  /// Creates a [PhotoResult].
  const PhotoResult({required this.bytes, required this.format});

  /// The encoded image bytes.
  final Uint8List bytes;

  /// Encoding of [bytes].
  final PhotoFormat format;
}

/// Encoded image format produced by [MetaWearablesDat.capturePhoto].
enum PhotoFormat {
  /// JPEG. Available on both iOS and Android.
  jpeg,

  /// HEIC / HEIF. Available on iOS; on Android availability depends on the
  /// device generation. Prefer [PhotoFormat.jpeg] for cross-platform
  /// portability.
  heic,
}
