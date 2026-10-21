import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';

void main() {
  group('searchMomentSeekFromSnippets', () {
    test('opens transcript seek when search query and timed snippet exist', () {
      final seek = searchMomentSeekFromSnippets(
        snippets: const [TranscriptMatchSnippet(text: 'budget review next week', start: 12.5, end: 16.0)],
        searchQuery: 'budget review',
      );
      expect(seek, isNotNull);
      expect(seek!.start, 12.5);
      expect(seek.end, 16.0);
    });

    test('falls back end to start when snippet end is missing', () {
      final seek = searchMomentSeekFromSnippets(
        snippets: const [TranscriptMatchSnippet(text: 'budget review', start: 4.0)],
        searchQuery: 'budget',
      );
      expect(seek!.start, 4.0);
      expect(seek.end, 4.0);
    });

    test('uses the first timed snippet when an earlier snippet is untimed', () {
      final seek = searchMomentSeekFromSnippets(
        snippets: const [
          TranscriptMatchSnippet(text: 'overview evidence'),
          TranscriptMatchSnippet(text: 'spoken match', start: 21.0, end: 24.0),
        ],
        searchQuery: 'spoken match',
      );
      expect(seek, isNotNull);
      expect(seek!.start, 21.0);
      expect(seek.end, 24.0);
    });

    test('returns null without search query (overview browse, not find-and-play)', () {
      expect(
        searchMomentSeekFromSnippets(
          snippets: const [TranscriptMatchSnippet(text: 'budget review', start: 1.0, end: 2.0)],
          searchQuery: '',
        ),
        isNull,
      );
    });

    test('returns null when snippets lack start (open overview, not seek)', () {
      expect(
        searchMomentSeekFromSnippets(
          snippets: const [TranscriptMatchSnippet(text: 'budget review')],
          searchQuery: 'budget',
        ),
        isNull,
      );
    });

    test('returns null when locked/empty snippets list', () {
      expect(searchMomentSeekFromSnippets(snippets: const [], searchQuery: 'budget'), isNull);
    });
  });
}
