import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/message.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('a day summary message is still a day summary after the chat cache round trip', () {
    final message = ServerMessage.fromJson({
      'id': 'message-1',
      'created_at': '2026-09-19T20:00:00Z',
      'text': 'Here is your day',
      'sender': 'ai',
      'type': 'day_summary',
    });
    expect(message.type, MessageType.daySummary);

    SharedPreferencesUtil().cachedMessages = [message];

    expect(SharedPreferencesUtil().cachedMessages.single.type, MessageType.daySummary);
  });
}
