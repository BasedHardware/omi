import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversations/background_conversations.dart';

ServerConversation _conversation(String title, {String? salience, int minutes = 5, bool starred = false}) {
  final start = DateTime.utc(2026, 10, 21, 13);
  return ServerConversation(
    id: title,
    createdAt: start,
    structured: Structured(title, '', salience: salience),
    startedAt: start,
    finishedAt: start.add(Duration(minutes: minutes)),
    starred: starred,
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
