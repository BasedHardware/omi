import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_header.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/ui/ui.dart';

TranscriptSegment _segment(String text) => TranscriptSegment(
      id: 'seg',
      text: text,
      speaker: 'SPEAKER_00',
      isUser: false,
      personId: null,
      start: 0,
      end: 1,
      translations: [],
    );

ServerConversation _conversation(
    {String title = 'Venue talk.', String overview = '', bool summaryRetryable = true, String? captureCoverage}) {
  return ServerConversation(
    id: 'detail-retry',
    createdAt: DateTime(2026, 9, 30, 12),
    structured: Structured(title, overview, emoji: '🧠'),
    transcriptSegments: [_segment('Venue talk. We picked Friday.')],
    summaryRetryable: summaryRetryable,
    captureCoverage: captureCoverage,
  );
}

ConversationDetailProvider _detail(ServerConversation conversation, {ConversationReprocessCall? reprocess}) {
  return ConversationDetailProvider(reprocess: reprocess)
    ..selectedDate = conversationLocalDayKey(conversation.createdAt)
    ..setCachedConversation(conversation)
    ..titleController = TextEditingController(text: conversation.structured.title)
    ..titleFocusNode = FocusNode();
}

Widget _app(ConversationDetailProvider detail, Widget body, {FolderProvider? folders}) {
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
      if (folders != null) ChangeNotifierProvider<FolderProvider>.value(value: folders),
    ],
    child: MaterialApp(
      theme: buildOmiTheme(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(body: body),
    ),
  );
}

Widget get _summary => const CustomScrollView(slivers: [GetAppsWidgets()]);

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('an empty summary on a retryable row offers Summary failed · Retry, which reprocesses', (tester) async {
    final gate = Completer<ServerConversation?>();
    final calls = <String>[];
    final detail = _detail(
      _conversation(),
      reprocess: (id, {appId, requireSpeakerReceipt = false}) {
        calls.add(id);
        return gate.future;
      },
    );
    addTearDown(detail.dispose);

    await tester.pumpWidget(_app(detail, _summary));
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));

    expect(find.byKey(const Key('conversation_detail_summary_retry')), findsOneWidget);
    expect(find.text(l10n.conversationSummaryFailed), findsOneWidget);
    expect(find.text(l10n.noSummaryForConversation), findsNothing);

    await tester.tap(find.text(l10n.retry));
    await tester.pump();
    expect(calls, ['detail-retry']);
    expect(find.text(l10n.summarizingConversation), findsOneWidget);

    gate.complete(_conversation(title: 'Venue planning', overview: 'Picked Friday.', summaryRetryable: false));
    await tester.pump();
    await tester.pump();
    expect(detail.conversation.summaryRetryable, isFalse);
    expect(find.byKey(const Key('conversation_detail_summary_retry')), findsNothing);
  });

  testWidgets('an empty summary without the server marker keeps the ordinary Generate Summary prompt', (tester) async {
    final detail = _detail(_conversation(summaryRetryable: false));
    addTearDown(detail.dispose);

    await tester.pumpWidget(_app(detail, _summary));
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));

    expect(find.byKey(const Key('conversation_detail_summary_retry')), findsNothing);
    expect(find.text(l10n.noSummaryForConversation), findsOneWidget);
  });

  testWidgets('an untitled legacy conversation hints its transcript text instead of Untitled', (tester) async {
    final detail = _detail(_conversation(title: '', summaryRetryable: false));
    final folders = FolderProvider(foldersFetcher: () async => []);
    addTearDown(detail.dispose);
    addTearDown(folders.dispose);

    await tester.pumpWidget(_app(detail, ConversationDetailHeader(onOpenRecordings: (_) {}), folders: folders));
    final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));

    final field = tester.widget<TextField>(find.descendant(
      of: find.byType(ConversationTitleField),
      matching: find.byType(TextField),
    ));
    expect(field.decoration!.hintText, 'Venue talk.');
    expect(field.decoration!.hintText, isNot(l10n.untitledConversation));
  });

  for (final coverage in <String?>['incomplete', 'mapped', 'unknown', null]) {
    testWidgets('detail shows partial recording only for incomplete coverage ($coverage)', (tester) async {
      final original = _conversation(captureCoverage: coverage);
      // Exercise the generated wire and app cache roundtrip before showing the header.
      final conversation = ServerConversation.fromJson(original.toGenerated().toJson());
      expect(conversation.captureCoverage, coverage);
      expect(ServerConversation.fromJson(conversation.toJson()).captureCoverage, coverage);
      final detail = _detail(conversation);
      final folders = FolderProvider(foldersFetcher: () async => []);
      addTearDown(detail.dispose);
      addTearDown(folders.dispose);
      await tester.pumpWidget(_app(detail, ConversationDetailHeader(onOpenRecordings: (_) {}), folders: folders));
      final badge = find.byKey(const Key('conversation_partial_recording'));
      expect(badge, coverage == 'incomplete' ? findsOneWidget : findsNothing);
      if (coverage == 'incomplete') {
        final l10n = AppLocalizations.of(tester.element(find.byType(Scaffold)));
        expect(find.text(l10n.partialRecording), findsOneWidget);
        await tester.pumpWidget(_app(
          detail,
          MediaQuery(
              data: const MediaQueryData(textScaler: TextScaler.linear(2)),
              child: ConversationDetailHeader(onOpenRecordings: (_) {})),
          folders: folders,
        ));
        expect(badge, findsOneWidget);
        expect(tester.takeException(), isNull);
      }
    });
  }

  test('existing nested coverage field is read without inferring coverage on legacy rows', () {
    final json = _conversation().toJson();
    json['capture_evidence'] = {'coverage': 'incomplete'};
    expect(ServerConversation.fromJson(json).captureCoverage, 'incomplete');
    json.remove('capture_evidence');
    expect(ServerConversation.fromJson(json).captureCoverage, isNull);
  });
}
