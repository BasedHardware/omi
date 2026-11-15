// Episode copies preserve the deferred state unless the caller explicitly overrides it.
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/gen/episodes_wire.g.dart';

void main() {
  test('episode metadata preserves the authoritative member Home step', () {
    final episode = Episode.fromGenerated(GeneratedEpisode.fromJson({
      'id': 'fixture',
      'status': 'closed',
      'started_at': '2026-11-15T09:00:00Z',
      'last_activity_at': '2026-11-15T09:01:00Z',
      'conversation_ids': ['member'],
      'members': [
        {
          'id': 'member',
          'started_at': '2026-11-15T09:00:00Z',
          'status': 'processing',
          'home_step': 'transcribing',
          'gist': 'A lightweight member preview'
        }
      ],
    }));
    expect(episode.members.single.homeStep, 'transcribing');
    expect(episode.members.single.structured.overview, 'A lightweight member preview');
  });
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
