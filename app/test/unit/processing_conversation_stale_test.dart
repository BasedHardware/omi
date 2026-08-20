import 'package:flutter_test/flutter_test.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';

void main() {
  test('a conversation processing for under 30 minutes is not stale', () {
    final started = DateTime.utc(2026, 8, 19, 12, 0);
    expect(
      processingConversationIsStale(started, now: started.add(const Duration(minutes: 29))),
      isFalse,
    );
  });

  test('a conversation processing for 30 minutes or more is stale and dismissible', () {
    final started = DateTime.utc(2026, 8, 19, 12, 0);
    expect(
      processingConversationIsStale(started, now: started.add(const Duration(minutes: 30))),
      isTrue,
    );
  });
}
