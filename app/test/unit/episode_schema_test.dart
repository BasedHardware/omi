// Episode copies preserve the deferred state unless the caller explicitly overrides it.
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/episode.dart';

void main() {
  final startedAt = DateTime.utc(2026, 11, 10);
  final deferred = Episode(
    id: 'deferred-episode',
    live: false,
    startedAt: startedAt,
    lastActivityAt: startedAt,
    composeDeferred: true,
  );

  test('copyWith can clear composeDeferred', () {
    expect(deferred.copyWith(composeDeferred: false).composeDeferred, isFalse);
    expect(deferred.composeDeferred, isTrue);
  });

  test('copyWith preserves composeDeferred without an override', () {
    expect(deferred.copyWith().composeDeferred, isTrue);
  });
}
