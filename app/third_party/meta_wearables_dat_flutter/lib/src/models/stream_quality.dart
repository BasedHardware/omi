/// Quality preset for [MetaWearablesDat.startStreamSession].
///
/// Each preset corresponds to a fixed resolution that Meta's SDK accepts on
/// both Ray-Ban Meta and Oakley Meta. Higher quality means more bandwidth
/// over Bluetooth and higher CPU on the I420 -> ARGB conversion path on
/// Android.
///
/// Frame rate is independent of [StreamQuality]. Pick from
/// [StreamQuality.fpsValues].
///
/// | Quality | Resolution (W x H) |
/// | ------- | ------------------ |
/// | low     | 360 x 640          |
/// | medium  | 504 x 896          |
/// | high    | 720 x 1280         |
enum StreamQuality {
  /// 360 x 640.
  low(0, 360, 640),

  /// 504 x 896. Default.
  medium(1, 504, 896),

  /// 720 x 1280. Highest CPU and bandwidth cost.
  high(2, 720, 1280);

  const StreamQuality(this.value, this.width, this.height);

  /// The integer used on the platform channel.
  final int value;

  /// Pixel width of frames at this quality.
  final int width;

  /// Pixel height of frames at this quality.
  final int height;

  /// Allowed values for the `fps` argument to
  /// [MetaWearablesDat.startStreamSession]. The SDK accepts only this
  /// discrete set; values outside the list are clamped to the closest
  /// supported FPS by Meta's SDK.
  static const List<int> fpsValues = [2, 7, 15, 24, 30];
}
