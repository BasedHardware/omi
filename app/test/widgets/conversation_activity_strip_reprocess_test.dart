import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_activity_strip.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/providers/conversation_provider.dart';

import '../helpers/reprocess_fakes.dart';

TranscriptSegment _segment(String text) => TranscriptSegment(
      id: 'seg-1',
      text: text,
      speaker: 'SPEAKER_00',
      isUser: false,
      personId: null,
      start: 0,
      end: 1,
      translations: [],
    );

ServerConversation _conversation({String overview = 'Old summary'}) {
  return ServerConversation(
    id: 'strip-reprocess',
    createdAt: DateTime(2026, 10, 17, 9, 30),
    structured: Structured('Choosing a Table', overview, emoji: '🍽️'),
    transcriptSegments: [_segment('Ice? No ice? Yeah.')],
    status: ConversationStatus.completed,
  );
}

ConversationDetailProvider _detail(
  ServerConversation conversation, {
  ConversationReprocessCall? reprocess,
}) {
  return ConversationDetailProvider(reprocess: reprocess)
    ..selectedDate = conversationLocalDayKey(conversation.createdAt)
    ..setCachedConversation(conversation)
    ..titleController = TextEditingController(text: conversation.structured.title)
    ..titleFocusNode = FocusNode();
}

Widget _app(ConversationDetailProvider detail, Widget body) {
  return ChangeNotifierProvider<ConversationDetailProvider>.value(
    value: detail,
    child: MaterialApp(
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: body),
    ),
  );
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  group('Activity strip while a reader reprocess runs off the Summary tab', () {
    testWidgets('shows the summarizing line when the Summary tab is not visible', (tester) async {
      final gate = Completer<ServerConversation?>();
      final detail = _detail(
        _conversation(),
        reprocess: conversationReprocess((id, {appId, requireSpeakerReceipt = false, forceOmi = false}) => gate.future),
      );
      addTearDown(detail.dispose);

      await tester.pumpWidget(
        _app(detail, const ConversationActivityStrip(summaryTabVisible: false)),
      );
      expect(find.byKey(const Key('conversation_activity_strip')), findsNothing);

      unawaited(detail.reprocessConversation(appId: null));
      await tester.pump();
      expect(detail.isReprocessingOpenConversation, isTrue);
      expect(find.byKey(const Key('conversation_activity_strip')), findsOneWidget);
      expect(find.text('Summarizing with Omi…'), findsOneWidget);
    });

    testWidgets('stays silent for a reader reprocess while the Summary tab is visible', (tester) async {
      final gate = Completer<ServerConversation?>();
      final detail = _detail(
        _conversation(),
        reprocess: conversationReprocess((id, {appId, requireSpeakerReceipt = false, forceOmi = false}) => gate.future),
      );
      addTearDown(detail.dispose);

      await tester.pumpWidget(_app(detail, const ConversationActivityStrip()));
      unawaited(detail.reprocessConversation());
      await tester.pump();
      // The Summary tab's own generating state is the progress surface.
      expect(find.byKey(const Key('conversation_activity_strip')), findsNothing);
      gate.complete(_conversation(overview: 'New summary'));
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 300));
      expect(find.byKey(const Key('conversation_activity_strip')), findsNothing);
    });
  });
}
