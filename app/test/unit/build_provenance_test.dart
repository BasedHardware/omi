import 'package:flutter_test/flutter_test.dart';
import 'package:omi/utils/build_provenance.dart';

void main() {
  test('fromEnvironment is unknown when dart-defines are omitted', () {
    final provenance = BuildProvenance.fromEnvironment();
    expect(provenance.gitSha, 'unknown');
    expect(provenance.buildNumber, 'unknown');
    expect(provenance.dirty, isFalse);
    expect(provenance.asProperties, {
      'git_sha': 'unknown',
      'build_number': 'unknown',
    });
  });

  test('dirty local builds mark the SHA', () {
    final provenance = BuildProvenance(
      gitSha: 'abc123def',
      buildNumber: '992',
      dirty: true,
    );
    expect(provenance.gitSha, 'abc123def-dirty');
    expect(provenance.buildNumber, '992');
    expect(provenance.asProperties['git_sha'], 'abc123def-dirty');
    expect(provenance.asProperties.containsKey('shorebird_patch'), isFalse);
  });

  test('empty SHA or build number become unknown', () {
    final provenance = BuildProvenance(gitSha: '', buildNumber: '', dirty: true);
    expect(provenance.gitSha, 'unknown');
    expect(provenance.buildNumber, 'unknown');
  });

  test('does not append -dirty twice or onto unknown', () {
    expect(
      BuildProvenance(gitSha: 'abc-dirty', buildNumber: '1', dirty: true).gitSha,
      'abc-dirty',
    );
    expect(
      BuildProvenance(gitSha: 'unknown', buildNumber: '1', dirty: true).gitSha,
      'unknown',
    );
  });
}
