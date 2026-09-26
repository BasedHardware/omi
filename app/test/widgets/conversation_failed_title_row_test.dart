import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/conversation_list_item.dart';
import 'package:omi/providers/conversation_provider.dart';

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
  List<TranscriptSegment>? segments,
  String emoji = '',
}) {
  return ServerConversation(
    id: id,
    createdAt: DateTime.utc(2020, 1, 1, 12),
    structured: Structured(title, '', emoji: emoji),
    status: status,
    transcriptSegments: segments ?? [_segment('one two three four five')],
  );
}

Finder get _indicator => find.byKey(const Key('conversation_failed_title_indicator'));
Finder get _reprocessButton => find.byKey(const Key('conversation_failed_title_reprocess_button'));

Future<ConversationProvider> _pumpRow(
  WidgetTester tester, {
  required ServerConversation conversation,
  Future<ServerConversation?> Function(String conversationId)? reprocess,
}) async {
  final provider = ConversationProvider(
    conversationListFetcher: () async => (items: <ServerConversation>[], ok: true),
    isSignedIn: () => true,
  )..conversations = [conversation];
  addTearDown(provider.dispose);

  await tester.pumpWidget(
    ChangeNotifierProvider<ConversationProvider>.value(
      value: provider,
      child: MaterialApp(
        navigatorKey: globalNavigatorKey,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: Consumer<ConversationProvider>(
            builder: (context, conversations, _) {
              if (conversations.conversations.isEmpty) {
                return conversations.processingConversations.isEmpty
                    ? const SizedBox.shrink()
                    : const Text('moved-to-processing');
              }
              return ConversationListItem(
                conversation: conversations.conversations.first,
                date: DateTime.utc(2020),
                conversationIdx: 0,
                reprocess: reprocess,
              );
            },
          ),
        ),
      ),
    ),
  );
  await tester.pump();
  return provider;
}

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('recoverable row shows the failed-title indicator and Reprocess', (tester) async {
    await _pumpRow(tester, conversation: _conversation());

    expect(_indicator, findsOneWidget);
    expect(_reprocessButton, findsOneWidget);
    expect(
      find.text(AppLocalizations.of(tester.element(find.byType(Scaffold))).conversationTitleDidntGenerate),
      findsOneWidget,
    );
    expect(
      find.text(AppLocalizations.of(tester.element(find.byType(Scaffold))).conversationReprocess),
      findsOneWidget,
    );
  });

  testWidgets('short transcript stays a quiet untitled row', (tester) async {
    await _pumpRow(
      tester,
      conversation: _conversation(segments: [_segment('one two three four')]),
    );

    expect(_indicator, findsNothing);
    expect(_reprocessButton, findsNothing);
  });

  testWidgets('titled rows do not show the failed-title affordance', (tester) async {
    await _pumpRow(
      tester,
      conversation: _conversation(title: 'Morning standup'),
    );

    expect(_indicator, findsNothing);
    expect(_reprocessButton, findsNothing);
  });

  testWidgets('Reprocess loading then processing result moves the row off the completed list', (tester) async {
    final gate = Completer<ServerConversation?>();
    final provider = await _pumpRow(
      tester,
      conversation: _conversation(),
      reprocess: (_) => gate.future,
    );

    await tester.tap(_reprocessButton);
    await tester.pump();
    expect(find.byType(CircularProgressIndicator), findsOneWidget);

    gate.complete(
      _conversation(status: ConversationStatus.processing, title: '', emoji: ''),
    );
    await tester.pumpAndSettle();

    expect(provider.processingConversations, hasLength(1));
    expect(provider.processingConversations.first.status, ConversationStatus.processing);
    expect(provider.conversations, isEmpty);
    expect(_indicator, findsNothing);
    expect(find.text('moved-to-processing'), findsOneWidget);
  });

  testWidgets('Reprocess titled result updates the row', (tester) async {
    final provider = await _pumpRow(
      tester,
      conversation: _conversation(),
      reprocess: (_) async => _conversation(title: 'Standup notes', emoji: '📝'),
    );

    await tester.tap(_reprocessButton);
    await tester.pumpAndSettle();

    expect(provider.conversations, hasLength(1));
    expect(provider.conversations.first.structured.title, 'Standup notes');
    expect(provider.processingConversations, isEmpty);
    expect(_indicator, findsNothing);
    expect(find.text('Standup notes'), findsOneWidget);
  });

  testWidgets('Reprocess failure keeps the recoverable row and shows a snackbar', (tester) async {
    await _pumpRow(
      tester,
      conversation: _conversation(),
      reprocess: (_) async => null,
    );

    await tester.tap(_reprocessButton);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(tester.takeException(), isNull);
    expect(_indicator, findsOneWidget);
    expect(_reprocessButton, findsOneWidget);
    expect(
      find.text(AppLocalizations.of(tester.element(find.byType(Scaffold))).somethingWentWrong),
      findsOneWidget,
    );
  });

  testWidgets('Reprocess thrown error keeps the recoverable row and shows a snackbar', (tester) async {
    await _pumpRow(
      tester,
      conversation: _conversation(),
      reprocess: (_) async {
        throw const FormatException('malformed reprocess body');
      },
    );

    await tester.tap(_reprocessButton);
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    expect(tester.takeException(), isNull);
    expect(_indicator, findsOneWidget);
    expect(
      find.text(AppLocalizations.of(tester.element(find.byType(Scaffold))).somethingWentWrong),
      findsOneWidget,
    );
  });
}
