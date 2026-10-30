import 'package:omi/backend/schema/review.dart';
import 'dream_review_context_fixture.dart';

/// Invented backend change receipt for tests and interactive offline UI checks.
ReviewChange dreamSyntheticChange({bool undone = false}) => ReviewChange(
      changeId: 'synthetic-spelling-change',
      kind: ReviewChangeKind.rename,
      editKind: 'spelling',
      title: 'Spelling',
      before: 'UL',
      after: 'URL',
      reason: 'The link spelling matches the surrounding conversation.',
      createdAt: DateTime.utc(2026, 10, 14, 12),
      context: dreamSpellingQuestion.spelling!.context,
      refs: const [ReviewChangeRef(type: 'conversation', id: 'synthetic-launch', label: 'Launch planning')],
      undone: undone,
    );
