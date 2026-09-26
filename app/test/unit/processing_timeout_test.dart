import 'package:flutter_test/flutter_test.dart';

import 'package:omi/utils/processing_timeout.dart';

void main() {
  final started = DateTime.utc(2026, 9, 7, 12, 0);

  test('processing under two minutes is not timed out', () {
    expect(
      isConversationProcessingTimedOut(
        conversationId: 'abc',
        processingStartedAt: started,
        now: started.add(const Duration(minutes: 1, seconds: 59)),
      ),
      isFalse,
    );
  });

  test('processing at exactly two minutes is timed out', () {
    expect(
      isConversationProcessingTimedOut(
        conversationId: 'abc',
        processingStartedAt: started,
        now: started.add(const Duration(minutes: 2)),
      ),
      isTrue,
    );
  });

  test('local placeholder conversations never time out', () {
    expect(
      isConversationProcessingTimedOut(
        conversationId: '0',
        processingStartedAt: started,
        now: started.add(const Duration(hours: 1)),
      ),
      isFalse,
    );
  });
}
