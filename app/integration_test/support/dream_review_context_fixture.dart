import 'package:omi/backend/schema/review.dart';

/// Synthetic wire response shared by the widget regression and interactive UI capture.
final dreamSpellingQuestion = ReviewItem.fromJson({
  'item_id': 'spelling:synthetic-link',
  'kind': 'spelling',
  'title': 'Which spelling?',
  'quote': 'UL',
  'source_ref': 'conversations/synthetic-launch#middle',
  'spelling': {
    'term_id': 'synthetic-link',
    'options': ['UL', 'URL'],
    'allow_custom': true,
    'context': {
      'conversation_title': 'Launch planning',
      'conversation_date': '2026-10-14T12:00:00Z',
      'main_index': 1,
      'quote_start': 16,
      'quote_end': 18,
      'segments': [
        {'text': 'Where should we send the link?', 'speaker_label': 'Alex', 'is_user': false},
        {'text': 'Please send the UL to the design group.', 'speaker_label': 'You', 'is_user': true},
        {'text': 'I will share it after lunch.', 'speaker_label': 'Alex', 'is_user': false},
      ],
    },
  },
})!;
