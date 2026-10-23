import 'dart:collection';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/episodes/live_episode_clock.dart';

/// Handoff probes for shared files outside the Home lane's edit ownership.
/// These report deterministic work and check content; the owning lane can turn
/// the printed observations into performance guards when it implements a fix.
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

  testWidgets('handoff: hidden live episode clock rebuild count', (tester) async {
    var builds = 0;
    final semantics = tester.ensureSemantics();
    try {
      await tester.pumpWidget(MaterialApp(
          home: TickerMode(
        enabled: false,
        child: LiveEpisodeClock(
            clock: () => DateTime(2020),
            builder: (_, now) {
              builds++;
              return const Text('Clock remains mounted');
            }),
      )));
      builds = 0;
      for (var i = 0; i < 5; i++) {
        await tester.pump(const Duration(seconds: 1));
      }
      debugPrint('HOME SHARED CLOCK: hidden semantics=true, 5 ticks, clockBuilds=$builds');
      expect(find.text('Clock remains mounted'), findsOneWidget);
      await tester.pumpWidget(const SizedBox.shrink());
    } finally {
      semantics.dispose();
    }
  });
}
