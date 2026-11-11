import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/gen/speaker_tag_prompts_wire.g.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/providers/conversation_provider.dart';

TranscriptSegment segment(String id, {bool owner = false}) => TranscriptSegment(
    id: id,
    text: 'Synthetic speech',
    speaker: 'SPEAKER_01',
    speakerId: 1,
    isUser: owner,
    personId: null,
    start: 0,
    end: 6,
    translations: []);

ServerConversation row(String id) => ServerConversation(
    id: id,
    createdAt: DateTime.utc(2026, 10, 9),
    structured: Structured('Synthetic', ''),
    transcriptSegments: [segment('played'), segment('sibling', owner: true)]);

void main() {
  test('server identities update only bound IDs in the returned conversation and every visible copy', () {
    final provider = ConversationProvider(isSignedIn: () => false);
    final canonical = row('c'), search = row('c'), group = row('c'), unrelated = row('another');
    provider.conversations = [canonical, unrelated];
    provider.searchedConversations = [search];
    provider.groupedConversations = {
      DateTime.utc(2026, 10, 9): [group]
    };
    provider.applySpeakerPromptIdentities(const GeneratedSpeakerTagPromptAnswerResponse(
      conversationId: 'c',
      qualityOutcome: 'owner_missed',
      segmentIdentities: [GeneratedSpeakerTagPromptSegmentIdentity(id: 'played', isUser: true)],
    ));
    for (final copy in [canonical, search, group]) {
      expect(copy.transcriptSegments[0].isUser, isTrue);
      expect(copy.transcriptSegments[0].speakerLabelSource, 'manual');
      expect(copy.transcriptSegments[1].isUser, isTrue);
      expect(copy.transcriptSegments[1].speakerLabelSource, isNull);
    }
    expect(unrelated.transcriptSegments[0].isUser, isFalse);
    provider.dispose();
  });
}
