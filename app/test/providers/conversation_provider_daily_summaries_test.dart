import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/conversation_provider.dart';

void main() {
  group('ConversationProvider daily recaps check', () {
    test('keeps the last answer when the check fails', () async {
      bool? answer = true;
      final provider = ConversationProvider(
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
        dailySummariesChecker: () async => answer,
        isSignedIn: () => true,
      );
      addTearDown(provider.dispose);

      await provider.checkHasDailySummaries();
      expect(provider.hasDailySummaries, isTrue);

      // The check could not be made: the Recaps tab must not disappear.
      answer = null;
      await provider.checkHasDailySummaries();
      expect(provider.hasDailySummaries, isTrue);
    });

    test('still applies a real empty answer', () async {
      final provider = ConversationProvider(
        conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
        dailySummariesChecker: () async => false,
        isSignedIn: () => true,
      );
      addTearDown(provider.dispose);

      await provider.checkHasDailySummaries();

      expect(provider.hasDailySummaries, isFalse);
    });
  });
}
