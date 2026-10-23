import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_speakers.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversations/background_conversations.dart';

ServerConversation _conversation(String title,
    {String? salience, int minutes = 5, bool starred = false, List<TranscriptSegment> segments = const []}) {
  final start = DateTime.utc(2026, 10, 21, 13);
  return ServerConversation(
    id: title,
    speakerResolution: const ConversationSpeakers(status: 'resolved', participantSpeakerIds: [0]),
    createdAt: start,
    structured: Structured(title, '', salience: salience),
    startedAt: start,
    finishedAt: start.add(Duration(minutes: minutes)),
    starred: starred,
    transcriptSegments: segments,
  );
}

void main() {
  test('only completed, unstarred background notes are left to the daily recap', () {
    expect(leftToDailyRecap(_conversation('TV', salience: 'background')), isTrue);
    expect(leftToDailyRecap(_conversation('Lunch', salience: 'highlight')), isFalse);
    expect(leftToDailyRecap(_conversation('Legacy')), isFalse);
    expect(leftToDailyRecap(_conversation('Kept', salience: 'background', starred: true)), isFalse);
    final processing = _conversation('Still going', salience: 'background')..status = ConversationStatus.processing;
    expect(leftToDailyRecap(processing), isFalse);
  });

  test('unavailable and legacy speaker resolution keep model background visible', () {
    final row = _conversation('At home', salience: 'background');
    final json = row.toJson();
    json['speaker_resolution'] = {'status': 'unavailable', 'participant_speaker_ids': <int>[]};
    expect(leftToDailyRecap(ServerConversation.fromJson(json)), isFalse);
    json.remove('speaker_resolution');
    expect(leftToDailyRecap(ServerConversation.fromJson(json)), isFalse);
  });

  test('owner dialogue stays on Home regardless of the notes topic or model vote', () {
    final row = _conversation('Laundry', salience: 'background', minutes: 29, segments: [
      for (var i = 0; i < 6; i++)
        TranscriptSegment(
            id: 's$i',
            text: 'Synthetic turn',
            speaker: 'SPEAKER_${i % 2}',
            speakerId: i % 2,
            isUser: i.isEven,
            personId: null,
            start: i * 2.0,
            end: i * 2.0 + 1,
            translations: []),
    ]);
    expect(leftToDailyRecap(row), isFalse);
  });

  test('locked and discarded rows are never moved to the recap', () {
    final json = _conversation('TV', salience: 'background').toJson();
    json['is_locked'] = true;
    expect(leftToDailyRecap(ServerConversation.fromJson(json)), isFalse);
    json['is_locked'] = false;
    json['discarded'] = true;
    expect(leftToDailyRecap(ServerConversation.fromJson(json)), isFalse);
  });

  test('salience survives the wire and the cache, and legacy notes have none', () {
    final fromWire = Structured.fromJson({'title': 't', 'overview': 'o', 'salience': 'background'});
    expect(fromWire.isBackground, isTrue);
    expect(Structured.fromJson(fromWire.toJson()).salience, 'background');
    expect(Structured.fromGenerated(fromWire.toGenerated()).salience, 'background');
    final legacy = Structured.fromJson({'title': 't', 'overview': 'o'});
    expect(legacy.salience, isNull);
    expect(legacy.toJson().containsKey('salience'), isFalse);
  });
}
