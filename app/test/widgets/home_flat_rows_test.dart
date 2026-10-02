/// Home's rows on the canvas are flat: a device tile at the start, the title, and a quiet second
/// line. A conversation, one still processing, a meeting that was not captured and what is
/// recording now all share the layout.
library;

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/capture_gap_list_item.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/pages/conversations/widgets/live_capture_card.dart';
import 'package:omi/pages/conversations/widgets/processing_capture.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/device_tile.dart';

void main() {
  late ConversationProvider provider;

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    provider = ConversationProvider(
      conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
      isSignedIn: () => true,
    );
  });
  tearDown(() => provider.dispose());

  Future<void> pump(WidgetTester tester, Widget child) async {
    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<ConversationProvider>.value(value: provider),
        ChangeNotifierProvider<ConnectivityProvider>(create: (_) => ConnectivityProvider()),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(body: OmiCanvas(child: child)),
      ),
    ));
    await tester.pump();
  }

  DeviceTile tile(WidgetTester tester) => tester.widget<DeviceTile>(find.byType(DeviceTile));

  final started = DateTime(2026, 9, 20, 10, 5);
  ServerConversation conversation({ConversationStatus status = ConversationStatus.completed}) => ServerConversation(
        id: 'a',
        createdAt: started,
        startedAt: started,
        finishedAt: started.add(const Duration(minutes: 21)),
        structured: Structured('Design review', 'Overview', emoji: '🧠'),
        status: status,
        source: ConversationSource.phone,
      );

  testWidgets('a conversation: its device, the title and the time, flat on the page', (tester) async {
    final row = conversation();
    provider.conversations = [row];
    await pump(tester, ConversationListItem(conversation: row, date: DateTime(2026, 9, 20), conversationIdx: 0));

    expect(tile(tester).source, 'phone');
    expect(find.text('🧠'), findsNothing, reason: 'the tile replaces the emoji');
    expect(find.text('Design review'), findsOneWidget);
    expect(find.textContaining('10:05'), findsOneWidget);
    expect(find.textContaining('21'), findsNothing, reason: 'the length is on the conversation page');

    final card = tester.widget<AnimatedContainer>(find.byKey(const ValueKey('conversation_card')));
    expect((card.decoration! as BoxDecoration).color, OmiColors.canvas,
        reason: 'the page colour, so the swipe-delete button behind stays hidden');
    final tileRect = tester.getRect(find.byType(DeviceTile));
    expect(tileRect.left, OmiSpacing.md, reason: 'on the page gutter, in line with the day labels');
    final cardRect = tester.getRect(find.byKey(const ValueKey('conversation_card')));
    expect(tileRect.top - cardRect.top, DeviceTile.rowPadding, reason: 'air above and below each row');
  });

  testWidgets('processing: the same row, its device faded, "Processing" over the start time', (tester) async {
    await pump(tester, ProcessingConversationWidget(conversation: conversation(status: ConversationStatus.processing)));

    expect(tile(tester).source, 'phone');
    expect(tile(tester).faded, isTrue);
    expect(find.text('Processing'), findsOneWidget);
    expect(find.textContaining('10:05'), findsOneWidget);
  });

  testWidgets('not captured: an empty dashed tile, the meeting and its time, and nothing to tap', (tester) async {
    await pump(
      tester,
      CaptureGapListItem(
        gap: CalendarCaptureGap(
          eventId: 'evt-1',
          title: 'Design review with Priya',
          startTime: DateTime.parse('2026-08-18T19:30:00Z'),
          endTime: DateTime.parse('2026-08-18T20:00:00Z'),
        ),
      ),
    );

    expect(tile(tester).missing, isTrue);
    expect(tile(tester).icon, Icons.event_busy);
    expect(find.text('Design review with Priya'), findsOneWidget);
    expect(find.byType(InkWell), findsNothing);
  });

  testWidgets('recording now: a green dot while live, grey when paused; trouble marks the words', (tester) async {
    Future<Color?> dot({bool paused = false, String? explanation}) async {
      await pump(
        tester,
        LiveCaptureCard(
          source: 'omi',
          status: 'Listening',
          paused: paused,
          explanation: explanation,
          elapsed: const Duration(minutes: 12, seconds: 4),
          lastLine: 'so we ship the widgets Friday',
          onPauseToggle: () {},
        ),
      );
      return tile(tester).status;
    }

    expect(await dot(), OmiColors.success);
    expect(tile(tester).source, 'omi');
    expect(tester.getRect(find.textContaining('so we ship')).left,
        greaterThanOrEqualTo(tester.getRect(find.text('Listening')).left),
        reason: 'the transcript line sits under the text, clear of the tile');
    expect(await dot(paused: true), OmiColors.textTertiary);
    expect(await dot(explanation: 'The pendant disconnected.'), isNull, reason: 'no dot on the tile');
    expect(find.byIcon(Icons.warning_amber_rounded), findsOneWidget, reason: 'the warning sits beside the word');
  });
}
