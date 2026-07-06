/// Camera facing for the Mock Device Kit
/// ([MetaWearablesDat.setMockCameraFacing]).
///
/// Only meaningful for mock devices; real Meta wearables expose a single
/// outward-facing camera and ignore this setting.
enum CameraFacing {
  /// Front-facing (selfie) camera on the host phone.
  front('front'),

  /// Back-facing (world) camera on the host phone.
  back('back');

  const CameraFacing(this.value);

  /// String value used on the platform channel.
  final String value;
}
