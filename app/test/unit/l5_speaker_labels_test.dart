import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/message_event.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/services/capture/speaker_suggestions.dart';

TranscriptSegment segment(String id, {String? source}) => TranscriptSegment(
    id: id,
    text: 'synthetic',
    speaker: 'SPEAKER_01',
    isUser: false,
    personId: source == 'manual' ? 'person' : null,
    speakerLabelSource: source,
    start: 0,
    end: 1,
    translations: []);
SpeakerLabelSuggestionEvent event({bool? isUser, String person = '', bool retracted = false}) =>
    SpeakerLabelSuggestionEvent(
        speakerId: 1,
        segmentId: 'a',
        personId: person,
        personName: retracted ? '' : 'Synthetic',
        isUser: isUser,
        retracted: retracted);
void main() {
  test('explicit owner is authoritative, sentinel is a legacy fallback', () {
    expect(event(isUser: true).resolvesOwner, isTrue);
    expect(event(person: 'user').resolvesOwner, isTrue);
    expect(event(isUser: false, person: 'user').resolvesOwner, isFalse);
    final wire = SpeakerLabelSuggestionEvent.fromJson(
        {'speaker_id': 1, 'segment_id': 'a', 'person_id': '', 'person_name': '', 'is_user': true});
    expect(wire.resolvesOwner, isTrue);
    expect(wire.speakerId, 1);
  });
  test('retraction reverts previously auto-applied owner and person, preserving manual edits', () {
    for (final owner in [true, false]) {
      final segments = [segment('a'), segment('b', source: 'manual')];
      final suggestions = <String, SpeakerLabelSuggestionEvent>{};
      final suggestion = event(isUser: owner, person: owner ? '' : 'resolved');
      expect(reconcileSpeakerSuggestion(suggestion, segments, [], suggestions, explicitOwner: true),
          SpeakerSuggestionDisposition.assignment);
      applyResolvedSpeakerSuggestion(suggestion, segments, []);
      expect(segments.first.isUser, owner);
      expect(segments.first.personId, owner ? null : 'resolved');
      expect(
          reconcileSpeakerSuggestion(event(retracted: true, isUser: false), segments, [], suggestions,
              explicitOwner: true),
          SpeakerSuggestionDisposition.reverted);
      expect(segments.first.isUser, isFalse);
      expect(segments.first.personId, isNull);
      expect(segments.last.personId, 'person');
    }
  });
  test('legacy serving path retains its labels on a retraction', () {
    final segments = [segment('a')];
    applyResolvedSpeakerSuggestion(event(isUser: true), segments, []);
    reconcileSpeakerSuggestion(event(retracted: true), segments, [], {});
    expect(segments.first.isUser, isTrue);
  });
  test('automatic corrections overwrite automatic labels and skip in-flight manual edits', () {
    final segments = [segment('a'), segment('b')];
    applyResolvedSpeakerSuggestion(event(isUser: true), segments, []);
    applyResolvedSpeakerSuggestion(event(isUser: false, person: 'resolved'), segments, ['b']);
    expect(segments.first.personId, 'resolved');
    expect(segments.first.isUser, isFalse);
    expect(segments.last.isUser, isTrue);
  });
}
