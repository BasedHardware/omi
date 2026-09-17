import 'package:flutter/foundation.dart';
import 'package:shorebird_code_push/shorebird_code_push.dart';

/// Compile-time identity of the running binary.
///
/// [gitSha] and [buildNumber] come from `--dart-define=OMI_GIT_SHA` /
/// `OMI_BUILD_NUMBER` (and `OMI_GIT_DIRTY=true` for a dirty worktree). When a
/// define is omitted the accessor is `'unknown'` — never an empty string, so a
/// PostHog / Crashlytics query for a real SHA cannot collide with a local
/// `flutter run` that forgot the flags.
///
/// Shorebird patches replace the Dart AOT snapshot but keep the store
/// [buildNumber]. The patched Dart's `OMI_GIT_SHA` is whatever was passed to
/// `shorebird patch` (the patch commit). The Shorebird-assigned patch *number*
/// is not a dart-define — it is assigned at publish time. [shorebirdPatchNumber]
/// reads it at runtime via `ShorebirdUpdater.readCurrentPatch` when the
/// updater is available; otherwise `'none'` (store binary, `flutter run`) or
/// `'unknown'` (read failed).
class BuildProvenance {
  BuildProvenance({
    required String gitSha,
    required String buildNumber,
    required this.dirty,
    this.shorebirdPatch = 'none',
  })  : gitSha = _resolveSha(gitSha, dirty),
        buildNumber = buildNumber.isEmpty ? 'unknown' : buildNumber;

  factory BuildProvenance.fromEnvironment({String shorebirdPatch = 'none'}) {
    const sha = String.fromEnvironment('OMI_GIT_SHA');
    const build = String.fromEnvironment('OMI_BUILD_NUMBER');
    const dirtyRaw = String.fromEnvironment('OMI_GIT_DIRTY');
    return BuildProvenance(
      gitSha: sha,
      buildNumber: build,
      dirty: dirtyRaw == 'true',
      shorebirdPatch: shorebirdPatch.isEmpty ? 'none' : shorebirdPatch,
    );
  }

  final String gitSha;
  final String buildNumber;
  final bool dirty;
  final String shorebirdPatch;

  static String _resolveSha(String sha, bool dirty) {
    if (sha.isEmpty) return 'unknown';
    if (sha == 'unknown') return 'unknown';
    if (dirty && !sha.endsWith('-dirty')) return '$sha-dirty';
    return sha;
  }

  Map<String, String> get asProperties => {
        'git_sha': gitSha,
        'build_number': buildNumber,
        'shorebird_patch': shorebirdPatch,
      };

  /// Override in tests. Production reads [ShorebirdUpdater.readCurrentPatch].
  @visibleForTesting
  static Future<String> Function()? patchNumberReaderForTesting;

  static Future<String> shorebirdPatchNumber() async {
    final injected = patchNumberReaderForTesting;
    if (injected != null) return injected();
    try {
      final updater = ShorebirdUpdater();
      if (!updater.isAvailable) return 'none';
      final patch = await updater.readCurrentPatch();
      if (patch == null) return 'none';
      return '${patch.number}';
    } catch (_) {
      return 'unknown';
    }
  }
}
