/// Compile-time identity of the running binary.
///
/// [gitSha] and [buildNumber] come from `--dart-define=OMI_GIT_SHA` /
/// `OMI_BUILD_NUMBER` (and `OMI_GIT_DIRTY=true` when a *tracked* file differs
/// from HEAD). When a define is omitted the accessor is `'unknown'` — never an
/// empty string, so a PostHog / Crashlytics query for a real SHA cannot collide
/// with a local `flutter run` that forgot the flags.
class BuildProvenance {
  BuildProvenance({
    required String gitSha,
    required String buildNumber,
    required this.dirty,
  })  : gitSha = _resolveSha(gitSha, dirty),
        buildNumber = buildNumber.isEmpty ? 'unknown' : buildNumber;

  factory BuildProvenance.fromEnvironment() {
    const sha = String.fromEnvironment('OMI_GIT_SHA');
    const build = String.fromEnvironment('OMI_BUILD_NUMBER');
    const dirtyRaw = String.fromEnvironment('OMI_GIT_DIRTY');
    return BuildProvenance(
      gitSha: sha,
      buildNumber: build,
      dirty: dirtyRaw == 'true',
    );
  }

  final String gitSha;
  final String buildNumber;
  final bool dirty;

  static String _resolveSha(String sha, bool dirty) {
    if (sha.isEmpty) return 'unknown';
    if (sha == 'unknown') return 'unknown';
    if (dirty && !sha.endsWith('-dirty')) return '$sha-dirty';
    return sha;
  }

  Map<String, String> get asProperties => {
        'git_sha': gitSha,
        'build_number': buildNumber,
      };
}
