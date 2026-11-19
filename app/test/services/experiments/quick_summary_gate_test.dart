import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/conversations_v3_provider.dart';

Future<void> _account(String uid, String answer) async {
  SharedPreferences.setMockInitialValues({if (answer.isNotEmpty) 'conversationsV3Answer': answer});
  await SharedPreferencesUtil.init();
  SharedPreferencesUtil().uid = uid;
}

void main() {
  // QuickSummaryGate requires this: a v3 account's capture ends as a recording that v3 summarises itself.
  group('ConversationsV3Provider.rememberedLegacy', () {
    test('is true only once the server answered "not v3" for this account', () async {
      await _account('u1', 'u1:0');
      expect(ConversationsV3Provider.rememberedLegacy(), isTrue);
    });

    test('is false for a v3 account', () async {
      await _account('u1', 'u1:1');
      expect(ConversationsV3Provider.rememberedLegacy(), isFalse);
    });

    test('is false before the first answer', () async {
      await _account('u1', '');
      expect(ConversationsV3Provider.rememberedLegacy(), isFalse);
    });

    test('never inherits another account\'s answer', () async {
      await _account('u2', 'u1:0');
      expect(ConversationsV3Provider.rememberedLegacy(), isFalse);
    });
  });
}
