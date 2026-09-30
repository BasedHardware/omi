import 'package:flutter/widgets.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/utils/analytics/registry/events.g.dart';
import 'package:omi/utils/conversations/conversation_title.dart';

TranscriptSegment _segment(String text) {
  return TranscriptSegment(
    id: 'seg',
    text: text,
    speaker: 'SPEAKER_00',
    isUser: false,
    personId: null,
    start: 0,
    end: 1,
    translations: [],
  );
}

ServerConversation _conversation({
  String id = 'c1',
  String title = '',
  ConversationStatus status = ConversationStatus.completed,
  List<TranscriptSegment> segments = const [],
  bool discarded = false,
  bool isLocked = false,
  bool summaryRetryable = false,
  DateTime? createdAt,
}) {
  return ServerConversation(
    id: id,
    createdAt: createdAt ?? DateTime.utc(2020),
    structured: Structured(title, ''),
    status: status,
    transcriptSegments: segments,
    discarded: discarded,
    isLocked: isLocked,
    summaryRetryable: summaryRetryable,
  );
}

Map<String, dynamic> _wire({Object? summaryRetryable, bool includeKey = true}) => {
      'id': 'c1',
      'created_at': '2026-09-30T12:00:00Z',
      'started_at': '2026-09-30T12:00:00Z',
      'finished_at': '2026-09-30T12:05:00Z',
      'structured': {'title': 'Venue planning', 'overview': ''},
      if (includeKey) 'summary_retryable': summaryRetryable,
    };

void main() {
  final l10n = lookupAppLocalizations(const Locale('en'));
  final emitted = <ConversationUntitledRendered>[];

  setUp(() {
    emitted.clear();
    UntitledConversationTelemetry.resetForTest();
    UntitledConversationTelemetry.sinkOverride = emitted.add;
  });

  tearDown(UntitledConversationTelemetry.resetForTest);

  group('ServerConversation.summaryRetryable wire', () {
    test('true parses and survives the cache round trip', () {
      final conversation = ServerConversation.fromJson(_wire(summaryRetryable: true));
      expect(conversation.summaryRetryable, isTrue);
      expect(ServerConversation.fromJson(conversation.toJson()).summaryRetryable, isTrue);
      expect(conversation.toGenerated().summaryRetryable, isTrue);
    });

    test('absent and null mean not retryable (every released server)', () {
      expect(ServerConversation.fromJson(_wire(includeKey: false)).summaryRetryable, isFalse);
      expect(ServerConversation.fromJson(_wire(summaryRetryable: null)).summaryRetryable, isFalse);
      expect(ServerConversation.fromJson(_wire(summaryRetryable: false)).summaryRetryable, isFalse);
      expect(ServerConversation.fromJson(_wire(includeKey: false)).toJson().containsKey('summary_retryable'), isFalse);
    });
  });

  group('ServerConversation.showsSummaryRetry', () {
    test('only the server marker offers Retry', () {
      expect(_conversation(summaryRetryable: true).showsSummaryRetry, isTrue);
      // A legacy empty-title row with a long transcript no longer guesses a retry.
      expect(_conversation(segments: [_segment('one two three four five six')]).showsSummaryRetry, isFalse);
    });

    test('discarded, locked and in-flight rows stay quiet', () {
      expect(_conversation(summaryRetryable: true, discarded: true).showsSummaryRetry, isFalse);
      expect(_conversation(summaryRetryable: true, isLocked: true).showsSummaryRetry, isFalse);
      expect(
        _conversation(summaryRetryable: true, status: ConversationStatus.processing).showsSummaryRetry,
        isFalse,
      );
    });
  });

  group('transcriptFallbackTitle', () {
    // The full server-parity vectors live in contracts/parity/deterministic_title.json and run in
    // test/parity/parity_contracts_test.dart; these pin the reviewed defects directly.
    test('the first sentence spans segments', () {
      final conversation = _conversation(segments: [_segment('We'), _segment('agreed on Friday.'), _segment('Next.')]);
      expect(transcriptFallbackTitle(conversation), 'We agreed on Friday.');
    });

    test('long text is cut at a word boundary within the server budget, with no ellipsis', () {
      final words = List.filled(20, 'venue').join(' ');
      final title = transcriptFallbackTitle(_conversation(segments: [_segment(words)]))!;
      expect(title.endsWith('…'), isFalse);
      expect(title.runes.length, lessThanOrEqualTo(conversationFallbackTitleMaxChars));
      expect(title.split(' ').every((word) => word == 'venue'), isTrue);
    });

    test('no transcript text is null', () {
      expect(transcriptFallbackTitle(_conversation()), isNull);
      expect(transcriptFallbackTitle(_conversation(segments: [_segment(' ')])), isNull);
    });
  });

  group('conversationDisplayTitle', () {
    test('a real title wins and emits nothing', () {
      final title = conversationDisplayTitle(
        _conversation(title: ' Standup '),
        l10n,
        surface: ConversationUntitledRenderedSurface.list,
      );
      expect(title, 'Standup');
      expect(emitted, isEmpty);
    });

    test('an untitled legacy row falls back to transcript text and emits nothing', () {
      final title = conversationDisplayTitle(
        _conversation(segments: [_segment('Lunch plans for Friday')]),
        l10n,
        surface: ConversationUntitledRenderedSurface.list,
      );
      expect(title, 'Lunch plans for Friday');
      expect(emitted, isEmpty);
    });

    test('bare untitled renders the fallback string and reports once per row and surface', () {
      final conversation = _conversation(createdAt: DateTime.now().subtract(const Duration(days: 3)));
      for (var i = 0; i < 3; i++) {
        expect(
          conversationDisplayTitle(conversation, l10n, surface: ConversationUntitledRenderedSurface.list),
          l10n.untitledConversation,
        );
      }
      conversationDisplayTitle(conversation, l10n, surface: ConversationUntitledRenderedSurface.map);
      conversationDisplayTitle(_conversation(id: 'c2'), l10n, surface: ConversationUntitledRenderedSurface.list);

      expect(emitted.map((event) => event.surface), [
        ConversationUntitledRenderedSurface.list,
        ConversationUntitledRenderedSurface.map,
        ConversationUntitledRenderedSurface.list,
      ]);
      expect(emitted.first.ageBucket, ConversationUntitledRenderedAgeBucket.under7d);
      // Bounded properties only: no id, title or transcript leaves the device.
      expect(emitted.first.properties.keys.toSet(), {'surface', 'age_bucket', 'summary_retryable'});
      expect(emitted.first.properties.values.whereType<String>().any((value) => value.contains('c1')), isFalse);
    });
  });

  test('the session budget saturates: past the cap nothing reports, and no earlier row re-reports', () {
    const cap = UntitledConversationTelemetry.maxReportsPerSession;
    for (var i = 0; i < cap + 10; i++) {
      conversationDisplayTitle(_conversation(id: 'row-$i'), l10n, surface: ConversationUntitledRenderedSurface.list);
    }
    expect(emitted, hasLength(cap));

    // Revisit every row, including the first ones a size-bounded cache would have evicted.
    for (var i = 0; i < cap + 10; i++) {
      conversationDisplayTitle(_conversation(id: 'row-$i'), l10n, surface: ConversationUntitledRenderedSurface.list);
    }
    expect(emitted, hasLength(cap));
  });

  test('age buckets', () {
    final now = DateTime.utc(2026, 9, 30, 12);
    ConversationUntitledRenderedAgeBucket bucket(Duration age) =>
        UntitledConversationTelemetry.ageBucketFor(now.subtract(age), now);
    expect(bucket(const Duration(minutes: 5)), ConversationUntitledRenderedAgeBucket.under1h);
    expect(bucket(const Duration(hours: 5)), ConversationUntitledRenderedAgeBucket.under1d);
    expect(bucket(const Duration(days: 2)), ConversationUntitledRenderedAgeBucket.under7d);
    expect(bucket(const Duration(days: 20)), ConversationUntitledRenderedAgeBucket.under30d);
    expect(bucket(const Duration(days: 400)), ConversationUntitledRenderedAgeBucket.over30d);
  });
}
