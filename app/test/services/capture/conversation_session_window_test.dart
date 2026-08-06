import 'package:flutter_test/flutter_test.dart';
import 'package:omi/services/capture/conversation_session_window.dart';

void main() {
  group('ConversationSessionWindow', () {
    test('binds audio captured before the initial server session event', () {
      final window = ConversationSessionWindow();

      expect(window.ensureStarted(100), 100);
      expect(window.observe(conversationId: 'conversation-a', nowSeconds: 102), 100);
      expect(
        window.complete(
          conversationId: 'conversation-a',
          fallbackStartSeconds: 0,
        ),
        100,
      );
    });

    test('folds empty server owners into the next completed conversation', () {
      final window = ConversationSessionWindow();

      window.ensureStarted(100);
      window.observe(conversationId: 'empty-a', nowSeconds: 101);
      window.observe(conversationId: 'empty-b', nowSeconds: 120);
      window.observe(conversationId: 'voiced-c', nowSeconds: 140);

      expect(
        window.complete(
          conversationId: 'voiced-c',
          fallbackStartSeconds: 140,
        ),
        100,
      );
      expect(window.nextStartSeconds, isNull);
    });

    test('keeps a later rollover boundary after an earlier conversation completes', () {
      final window = ConversationSessionWindow();

      window.observe(conversationId: 'conversation-a', nowSeconds: 100);
      window.observe(conversationId: 'conversation-b', nowSeconds: 220);

      expect(
        window.complete(
          conversationId: 'conversation-a',
          fallbackStartSeconds: 100,
        ),
        100,
      );
      expect(window.nextStartSeconds, 220);
      expect(
        window.complete(
          conversationId: 'conversation-b',
          fallbackStartSeconds: 220,
        ),
        220,
      );
    });

    test('does not duplicate a replayed session boundary', () {
      final window = ConversationSessionWindow();

      window.observe(conversationId: 'conversation-a', nowSeconds: 100);
      window.observe(conversationId: 'conversation-a', nowSeconds: 180);

      expect(
        window.complete(
          conversationId: 'conversation-a',
          fallbackStartSeconds: 180,
        ),
        100,
      );
      expect(window.nextStartSeconds, isNull);
    });
  });
}
