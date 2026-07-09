/// Resolution of the active video stream.
///
/// Emitted by [MetaWearablesDat.videoStreamSizeStream] once per resolution
/// change so a host app can size its `Texture` widget correctly:
///
/// ```dart
/// final size = await stream.first;
/// AspectRatio(
///   aspectRatio: size.width / size.height,
///   child: Texture(textureId: textureId),
/// );
/// ```
class VideoStreamSize {
  /// Creates a [VideoStreamSize].
  const VideoStreamSize({required this.width, required this.height});

  /// Constructs a [VideoStreamSize] from a platform-channel map.
  factory VideoStreamSize.fromMap(Map<Object?, Object?> map) {
    return VideoStreamSize(
      width: (map['width'] as num?)?.toInt() ?? 0,
      height: (map['height'] as num?)?.toInt() ?? 0,
    );
  }

  /// Pixel width.
  final int width;

  /// Pixel height.
  final int height;

  /// Convenience for `width / height`. Returns `0` when `height` is zero
  /// rather than `NaN`.
  double get aspectRatio => height == 0 ? 0 : width / height;

  @override
  String toString() => 'VideoStreamSize(${width}x$height)';
}
