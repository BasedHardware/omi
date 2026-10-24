import 'dart:collection';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// Counts actual element reads, including iterator/indexWhere walks. No host timing.
class _Reads<T> extends ListBase<T> {
  _Reads(this.items);
  final List<T> items;
  int reads = 0;
  @override
  int get length => items.length;
  @override
  set length(int value) => items.length = value;
  @override
  T operator [](int index) {
    reads++;
    return items[index];
  }

  @override
  void operator []=(int index, T value) => items[index] = value;
}

ServerConversation _conversation(int i, {List<TranscriptSegment> segments = const []}) => ServerConversation(
      id: 'c$i',
      createdAt: DateTime(2020),
      startedAt: DateTime(2020),
      finishedAt: DateTime(2020, 1, 1, 0, 2),
      structured: Structured('Conversation $i', 'Overview'),
      transcriptSegments: segments,
    );
TranscriptSegment _segment(String text, int i) => TranscriptSegment(
      id: 's$i',
      text: text,
      speaker: 'SPEAKER_0',
      isUser: true,
      personId: null,
      start: i.toDouble(),
      end: i + 1.0,
      translations: const [],
    );
Widget _app(ConversationProvider provider, List<ServerConversation> visible) =>
    ChangeNotifierProvider<ConversationProvider>.value(
      value: provider,
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(
            body: ListView(children: [
          for (final c in visible)
            ConversationListItem(key: ValueKey(c.id), conversation: c, date: c.createdAt, conversationIdx: -1),
        ])),
      ),
    );

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });
  for (final semantics in [false, true]) {
    testWidgets('row selectors do bounded work on no-op notifies (semantics=$semantics)', (tester) async {
      final handle = semantics ? tester.ensureSemantics() : null;
      try {
        tester.view.physicalSize = const Size(800, 1600);
        tester.view.devicePixelRatio = 1;
        addTearDown(tester.view.resetPhysicalSize);
        addTearDown(tester.view.resetDevicePixelRatio);
        final history = _Reads(List.generate(2000, _conversation));
        final visible = history.items.sublist(1992);
        final provider = ConversationProvider(isSignedIn: () => false)..conversations = history;
        addTearDown(provider.dispose);
        await tester.pumpWidget(_app(provider, visible));
        await tester.pump();
        history.reads = 0;
        var rowContentBuilds = 0;
        final previous = debugOnRebuildDirtyWidget;
        debugOnRebuildDirtyWidget = (element, builtOnce) {
          if (element.widget.runtimeType.toString() == '_SwipeDeleteRow') rowContentBuilds++;
          previous?.call(element, builtOnce);
        };
        try {
          for (var i = 0; i < 20; i++) {
            provider.notifyListeners();
            await tester.pump();
          }
        } finally {
          debugOnRebuildDirtyWidget = previous;
        }
        debugPrint('HOME ROWS semantics=$semantics: 20 notifies, historyReads=${history.reads}, '
            'rowContentBuilds=$rowContentBuilds');
        expect(history.reads, 0, reason: 'a visible row already owns its model; never search all history per notify');
        expect(rowContentBuilds, 0);
        visible.last.starred = true;
        provider.notifyListeners();
        await tester.pump();
        expect(find.byWidgetPredicate((w) => w is Semantics && w.properties.label == 'Starred'), findsOneWidget);
        provider.enterSelectionMode();
        await tester.pump();
        expect(tester.takeException(), isNull);
        await tester.pumpWidget(const SizedBox.shrink());
      } finally {
        handle?.dispose();
      }
    });
  }
  test('discarded/deferred snippet reads only the visible prefix of a long transcript', () {
    final segments = _Reads(List.generate(2000, (i) => _segment('Line $i has enough words to fill a preview.', i)));
    final c = _conversation(0, segments: segments);
    final expected = _oldSnippet(c);
    segments.reads = 0;
    final actual = conversationSnippet(c);
    debugPrint('HOME SNIPPET: 2000 segments, reads=${segments.reads}, chars=${actual.length}');
    expect(actual, expected);
    expect(segments.reads, lessThanOrEqualTo(5));
  });
  test('bounded snippets preserve trimming, word boundaries and ellipsis', () {
    for (final texts in <List<String>>[
      [],
      ['', '  ', '\n'],
      ['  hello ', '', ' world  '],
      ['x' * 2000],
      [' word ' * 2000],
      ['a' * 160, 'b'],
      ['a' * 159, 'b'],
      ['a' * 80, 'b' * 100],
      ['A short sentence.', '\n Another sentence.'],
    ]) {
      final c = _conversation(0, segments: [for (var i = 0; i < texts.length; i++) _segment(texts[i], i)]);
      for (final max in [0, 1, 10, 80, 160, 200]) {
        expect(conversationSnippet(c, maxChars: max), _oldSnippet(c, maxChars: max), reason: 'maxChars=$max');
      }
    }
  });
}

String _oldSnippet(ServerConversation c, {int maxChars = 160}) {
  final text = c.transcriptSegments.map((s) => s.text.trim()).where((t) => t.isNotEmpty).join(' ');
  if (text.length <= maxChars) return text;
  final cut = text.substring(0, maxChars);
  final space = cut.lastIndexOf(' ');
  return '${space > maxChars ~/ 2 ? cut.substring(0, space) : cut}…';
}
