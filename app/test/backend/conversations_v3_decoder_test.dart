// Owns synthetic additive-wire and capture-identity decoder contracts.
// Current source coverage does not certify a distributed released build.
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/home_feed_wire.g.dart' as feed;

// Current-source decoders; distribution-attested released replay remains pending.
void main() {
  final base = <String, dynamic>{
    'id': 'synthetic-conversation',
    'created_at': '2026-11-16T10:00:00Z',
    'started_at': '2026-11-16T10:00:00Z',
    'finished_at': '2026-11-16T10:05:00Z',
    'source': 'omi',
    'status': 'completed',
    'structured': {'title': 'Planning the next visit', 'overview': 'A synthetic summary', 'emoji': '🌳'},
    'transcript_segments': [
      {'text': 'Synthetic speech inside this conversation.', 'start': 0.0, 'end': 4.0, 'is_user': true}
    ],
  };
  test('additive v3 fields preserve the existing conversation decoder', () {
    final row = ServerConversation.fromJson({
      ...base,
      'kind': 'conversation',
      'home_hidden': false,
      'tile_state': 'done',
      'title_locked': true,
      'recording_pieces': [
        {'recording_id': 'r', 'audio_file_id': 'f', 'start': 12.5, 'end': 25.0}
      ],
      'summary_covers_through': '2026-11-16T10:05:00Z',
    });
    expect(row.id, base['id']);
    expect(row.structured.title, 'Planning the next visit');
    expect(row.transcriptSegments.single.text, 'Synthetic speech inside this conversation.');
    expect(row.isHiddenFromDefaultList, false);
  });
  test('capture socket payload preserves recording identity and donor bridge', () {
    final live = ServerConversation.fromJson({...base, 'id': 'recording', 'status': 'in_progress', 'recording': true});
    expect(live.id, 'recording');
    final completed = ServerConversation.fromJson({...base, 'id': 'recording', 'sync_merged_into': 'covering'});
    expect(completed.id, 'recording');
    expect(completed.isMergedDonor, true);
  });
  test('v3 Home uses the existing closed kind vocabulary', () {
    final card = feed.GeneratedHomeFeedCard.fromJson({
      'id': 'c', 'kind': 'conversation', 'detail_id': 'c', 'sort_at': base['created_at'],
      'status': 'completed', 'revision': 'synthetic',
    });
    expect(card.kind, 'conversation');
  });
}
