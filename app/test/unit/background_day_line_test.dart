import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversations/widgets/background_day_line.dart';

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

String _length(int seconds) => '${seconds ~/ 60}m';

void main() {
  test('only completed, unstarred background notes fold into the day line', () {
    expect(foldsIntoBackgroundLine(_conversation('TV', salience: 'background')), isTrue);
    expect(foldsIntoBackgroundLine(_conversation('Lunch', salience: 'highlight')), isFalse);
    expect(foldsIntoBackgroundLine(_conversation('Legacy')), isFalse);
    expect(foldsIntoBackgroundLine(_conversation('Kept', salience: 'background', starred: true)), isFalse);
    final processing = _conversation('Still going', salience: 'background')..status = ConversationStatus.processing;
    expect(foldsIntoBackgroundLine(processing), isFalse);
  });

  test('the line names each conversation with its length, then how many more', () {
    final background = [
      _conversation('TV in the background', salience: 'background', minutes: 32),
      _conversation('A note to self', salience: 'background', minutes: 0),
      _conversation('Short exchange', salience: 'background', minutes: 1),
      _conversation('Errand', salience: 'background'),
      _conversation('Radio', salience: 'background'),
    ];
    expect(
        backgroundLineItems(background, _length), 'TV in the background 32m · A note to self · Short exchange 1m · +2');
    expect(backgroundLineItems(background.take(1).toList(), _length), 'TV in the background 32m');
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
