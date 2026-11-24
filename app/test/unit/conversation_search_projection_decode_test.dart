// Search DTO round trips must retain the optional Home presentation field.
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';

void main() {
  for (final step in <String?>['failed', 'writing_notes', null]) {
    test('search decoder preserves home_step=$step and generated normalization', () {
      final item = ServerConversation(
              id: 'search',
              createdAt: DateTime.utc(2026, 11, 8),
              structured: Structured('Planning', ''),
              status: ConversationStatus.processing)
          .toJson();
      if (step != null) item['home_step'] = step;
      final decoded = decodeConversationSearchResponse({
        'items': [item],
        'current_page': 1,
        'per_page': 1,
        'total_pages': 2,
      });
      expect(decoded.isSuccess, isTrue);
      expect(decoded.items.single.homeStep, step);
      expect(decoded.items.single.status, ConversationStatus.processing);
      expect(decoded.items.single.structured.title, 'Planning');
      expect(decoded.currentPage, 1);
      expect(decoded.totalPages, 2);
    });
  }
}
