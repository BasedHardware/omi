import 'dart:collection';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/episodes/live_episode_clock.dart';

/// Counts element reads without using shared-host wall-clock timings.
class _Segments extends ListBase<TranscriptSegment> {
  final items = List.generate(
      2000,
      (i) => TranscriptSegment(
            id: 's$i',
            text: 'Words $i',
            speaker: 'SPEAKER_0',
            isUser: true,
            personId: null,
            start: i.toDouble(),
            end: i + 1.0,
            translations: const [],
          ));
  int reads = 0;
  @override
  int get length => items.length;
  @override
  set length(int value) => items.length = value;
  @override
  TranscriptSegment operator [](int index) {
    reads++;
    return items[index];
  }

  @override
  void operator []=(int index, TranscriptSegment value) => items[index] = value;
}

void main() {
  test('off-limits page identity signature scans the entire history on every notify', () {
    final rows = _Segments();
    int identitySignature(Iterable<Object> values) => Object.hashAll(values.map(identityHashCode));
    final initial = identitySignature(rows);
    rows.reads = 0;
    for (var i = 0; i < 20; i++) {
      expect(identitySignature(rows), initial);
    }
    debugPrint('HOME PAGE SIGNATURE COPY: 2000 rows, 20 no-op notifies, reads=${rows.reads}');
    expect(rows.reads, 40000);
  });

  test('duration must observe same-length segment replacement and timestamp mutation', () {
    final segments = _Segments();
    final c = ServerConversation(
      id: 'mutable',
      createdAt: DateTime(2020),
      structured: Structured('Title', ''),
      transcriptSegments: segments,
    );
    expect(c.getDurationInSeconds(), 2000);
    segments.items.last.end = 3000;
    expect(c.getDurationInSeconds(), 3000);
    segments.items.last = segments.items.first;
    expect(c.getDurationInSeconds(), 1999);
  });

  testWidgets('handoff: saved row title and duration traversal counts', (tester) async {
    final segments = _Segments();
    final c = ServerConversation(
        id: 'saved',
        createdAt: DateTime(2020),
        structured: Structured('Ordinary title without citations', ''),
        transcriptSegments: segments);
    final semantics = tester.ensureSemantics();
    try {
      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Builder(builder: (context) => Text(conversationRowTitle(context, c))),
      ));
      expect(find.text('Ordinary title without citations'), findsOneWidget);
      final titleReads = segments.reads;
      segments.reads = 0;
      expect(c.getDurationInSeconds(), 2000);
      debugPrint('HOME SHARED WORK: 2000 segments, ordinaryTitleReads=$titleReads, durationReads=${segments.reads}');
      await tester.pumpWidget(const SizedBox.shrink());
    } finally {
      semantics.dispose();
    }
  });

  for (final semanticsEnabled in [false, true]) {
    testWidgets('live episode clock stops hidden ticks and catches up (semantics=$semanticsEnabled)', (tester) async {
      var builds = 0;
      var enabled = false;
      var now = DateTime(2020);
      late StateSetter changeVisibility;
      final semantics = semanticsEnabled ? tester.ensureSemantics() : null;
      final clock = LiveEpisodeClock(
        clock: () => now,
        builder: (_, time) {
          builds++;
          return Text(time.toIso8601String());
        },
      );
      try {
        await tester.pumpWidget(MaterialApp(home: StatefulBuilder(builder: (context, setState) {
          changeVisibility = setState;
          return TickerMode(enabled: enabled, child: clock);
        })));
        builds = 0;
        for (var i = 0; i < 5; i++) {
          now = now.add(const Duration(seconds: 1));
          await tester.pump(const Duration(seconds: 1));
        }
        final hiddenBuilds = builds;
        changeVisibility(() => enabled = true);
        await tester.pump();
        expect(find.text(now.toIso8601String()), findsOneWidget, reason: 'catch up before another tick');
        builds = 0;
        for (var i = 0; i < 5; i++) {
          now = now.add(const Duration(seconds: 1));
          await tester.pump(const Duration(seconds: 1));
        }
        final visibleBuilds = builds;
        debugPrint(
            'HOME SHARED CLOCK: semantics=$semanticsEnabled, 5 ticks, hidden=$hiddenBuilds visible=$visibleBuilds');
        expect(hiddenBuilds, 0);
        expect(visibleBuilds, 5);
        await tester.pumpWidget(const SizedBox.shrink());
      } finally {
        await tester.pumpWidget(const SizedBox.shrink());
        semantics?.dispose();
      }
    });
  }
}
