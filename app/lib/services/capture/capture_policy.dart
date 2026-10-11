import 'dart:convert';

/// The durable authorization for every capture path.
///
/// The representation is deliberately small and strict because it is read by
/// the native background capture implementations as well as by Dart.  Keep
/// the field names, types, and version semantics aligned with the platform
/// parsers and with `test/fixtures/capture_policy.json`.
class CapturePolicy {
  static const int currentVersion = 1;

  const CapturePolicy({required this.revision, required this.muted}) : assert(revision >= 0);

  final int revision;
  final bool muted;

  int get version => currentVersion;

  Map<String, Object> toJson() => <String, Object>{
        'version': currentVersion,
        'revision': revision,
        'muted': muted,
      };

  String encode() => jsonEncode(toJson());

  /// Parses the canonical JSON representation.
  ///
  /// Parsing is intentionally stricter than Dart's usual `as` conversions:
  /// JSON booleans must be booleans and JSON numbers must be an integer.  This
  /// keeps Dart, Android, and iOS from disagreeing about a policy such as
  /// `{"muted": 1}` or `{"revision": 1.0}`.
  factory CapturePolicy.fromJson(Map<String, dynamic> json) {
    final version = json['version'];
    if (json.length != 3 || version is! int || version != currentVersion) {
      throw const FormatException('Unsupported capture policy version');
    }

    final revision = json['revision'];
    final muted = json['muted'];
    if (revision is! int || revision < 0 || muted is! bool) {
      throw const FormatException('Invalid capture policy fields');
    }

    return CapturePolicy(revision: revision, muted: muted);
  }

  /// Parses an encoded canonical policy, returning null for every invalid
  /// representation.  Callers choose the appropriate fail-closed fallback.
  static CapturePolicy? tryParse(String? encoded) {
    if (encoded == null || encoded.isEmpty) return null;
    try {
      final decoded = jsonDecode(encoded);
      if (decoded is! Map<String, dynamic>) return null;
      return CapturePolicy.fromJson(decoded);
    } on FormatException {
      return null;
    } on Object {
      return null;
    }
  }

  static CapturePolicy fromLegacy({required bool deviceMuted, required bool batchMuted}) =>
      CapturePolicy(revision: 0, muted: deviceMuted || batchMuted);

  @override
  bool operator ==(Object other) => other is CapturePolicy && other.revision == revision && other.muted == muted;

  @override
  int get hashCode => Object.hash(revision, muted);

  @override
  String toString() => 'CapturePolicy(revision: $revision, muted: $muted)';
}
