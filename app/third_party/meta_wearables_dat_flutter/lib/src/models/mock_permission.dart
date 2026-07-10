/// A wearable-side permission that the Mock Device Kit can pre-populate.
enum MockPermission {
  /// Camera permission (Meta AI camera-access bottom sheet on real devices).
  camera('camera');

  const MockPermission(this.value);

  /// String passed to the native side over the method channel.
  final String value;
}

/// The status the Mock Device Kit should report for a given [MockPermission].
enum MockPermissionStatus {
  /// Permission is granted.
  granted('granted'),

  /// Permission has been denied.
  denied('denied');

  const MockPermissionStatus(this.value);

  /// String passed to the native side over the method channel.
  final String value;
}
