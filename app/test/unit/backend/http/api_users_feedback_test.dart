import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/http/api/users.dart';

void main() {
  test('accepts only a durable bounded mobile feedback receipt', () {
    final receipt = MobileFeedbackReceipt.fromJson(
      {
        'schema_version': 'mobile_feedback_receipt.v1',
        'feedback_id': 'feedback-1',
        'event_id': 'event-1',
        'created': true,
        'persisted': true,
      },
      expectedFeedbackId: 'feedback-1',
    );

    expect(receipt?.feedbackId, 'feedback-1');
    expect(receipt?.eventId, 'event-1');
    expect(receipt?.created, isTrue);
  });

  test('rejects a 201-shaped receipt without persistence or event identity', () {
    final base = <String, dynamic>{
      'schema_version': 'mobile_feedback_receipt.v1',
      'feedback_id': 'feedback-1',
      'event_id': 'event-1',
      'created': false,
      'persisted': true,
    };

    expect(
      MobileFeedbackReceipt.fromJson({...base, 'persisted': false}, expectedFeedbackId: 'feedback-1'),
      isNull,
    );
    expect(
      MobileFeedbackReceipt.fromJson({...base, 'event_id': ''}, expectedFeedbackId: 'feedback-1'),
      isNull,
    );
    expect(
      MobileFeedbackReceipt.fromJson({...base, 'feedback_id': 'other'}, expectedFeedbackId: 'feedback-1'),
      isNull,
    );
    expect(
      MobileFeedbackReceipt.fromJson(
        {
          'feedback_id': 'feedback-1',
          'event_id': 'event-1',
          'created': true,
        },
        expectedFeedbackId: 'feedback-1',
      ),
      isNull,
    );
  });
}
