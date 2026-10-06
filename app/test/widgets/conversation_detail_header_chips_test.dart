import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_header.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/ui/ui.dart';

void main() {
  Future<void> pumpHeader(
    WidgetTester tester, {
    required double width,
    double textScale = 1,
    Folder? folder,
    bool youSpoke = false,
  }) async {
    tester.view.physicalSize = Size(width, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    final conversation = ServerConversation(
      id: 'chips',
      createdAt: DateTime(2026, 9, 28, 19, 50),
      startedAt: DateTime(2026, 9, 28, 19, 50),
      finishedAt: DateTime(2026, 9, 28, 19, 52, 42),
      structured: Structured('A title', ''),
      folderId: folder?.id,
      transcriptSegments: [
        if (youSpoke)
          TranscriptSegment(
            id: 's1',
            text: 'Hello',
            speaker: 'SPEAKER_00',
            isUser: true,
            personId: null,
            start: 0,
            end: 2,
            translations: [],
          ),
      ],
    );
    final detail = ConversationDetailProvider()
      ..selectedDate = conversationLocalDayKey(conversation.createdAt)
      ..setCachedConversation(conversation)
      ..titleController = TextEditingController(text: conversation.structured.title)
      ..titleFocusNode = FocusNode();
    final folders = FolderProvider(foldersFetcher: () async => [if (folder != null) folder]);
    await folders.loadFolders();
    addTearDown(detail.dispose);
    addTearDown(folders.dispose);

    await tester.pumpWidget(
      MultiProvider(
        providers: [
          ChangeNotifierProvider<ConversationDetailProvider>.value(value: detail),
          ChangeNotifierProvider<FolderProvider>.value(value: folders),
        ],
        child: MaterialApp(
          theme: buildOmiTheme(),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          builder: (context, child) => MediaQuery(
            data: MediaQuery.of(context).copyWith(textScaler: TextScaler.linear(textScale)),
            child: child!,
          ),
          home: Scaffold(body: ConversationDetailHeader(onOpenRecordings: (_) {})),
        ),
      ),
    );
    await tester.pump();
  }

  /// Every chip shown sits on the time's line, after the one before it, inside the page gutter.
  void expectOneLine(WidgetTester tester, double width) {
    final rects = [
      for (final key in ['conversation_when', 'conversation_folder', 'conversation_people'])
        if (find.byKey(Key(key)).evaluate().isNotEmpty) tester.getRect(find.byKey(Key(key))),
    ];
    expect(rects.length, greaterThan(1), reason: 'a line of chips to check');
    for (var i = 1; i < rects.length; i++) {
      expect(rects[i].center.dy, closeTo(rects[0].center.dy, 0.5), reason: 'beside the time, never below');
      expect(rects[i].left, greaterThan(rects[i - 1].right));
    }
    expect(rects.last.right, lessThanOrEqualTo(width - OmiSpacing.md + 0.5), reason: 'inside the page gutter');
    expect(tester.takeException(), isNull);
  }

  // Only a filed conversation shows its folder chip, so the one-line cases file it.
  Folder workFolder() {
    return Folder(
      id: 'f1',
      name: 'Work',
      color: '#6B7280',
      icon: 'folder',
      createdAt: DateTime(2026),
      updatedAt: DateTime(2026),
      order: 0,
      isDefault: false,
      isSystem: false,
      conversationCount: 1,
    );
  }

  testWidgets('the time and the folder stay on one line with large text on a small phone', (tester) async {
    // The case that wrapped: "Yesterday 7:50 PM · 2m 42s" and its folder at a large text size.
    await pumpHeader(tester, width: 375, textScale: 1.35, folder: workFolder());
    expectOneLine(tester, 375);
    final when = find.byKey(const Key('conversation_when'));
    expect(tester.getRect(when).width, lessThan(tester.getSize(when).width), reason: 'the pair shrank to fit');
  });

  testWidgets('who spoke shares the line with the time and the folder', (tester) async {
    await pumpHeader(tester, width: 1000, folder: workFolder(), youSpoke: true);
    expect(find.byKey(const Key('conversation_people')), findsOneWidget);
    expectOneLine(tester, 1000);
  });

  testWidgets('with large text on a small phone, who spoke stays on the line too', (tester) async {
    await pumpHeader(tester, width: 375, textScale: 1.35, folder: workFolder(), youSpoke: true);
    expectOneLine(tester, 375);
  });

  testWidgets('when the pair fits, nothing shrinks', (tester) async {
    // Test text is Ahem, a square per glyph, so "fits" needs more room than SF Pro would.
    await pumpHeader(tester, width: 1000, folder: workFolder());
    expectOneLine(tester, 1000);
    final when = find.byKey(const Key('conversation_when'));
    expect(tester.getRect(when).width, closeTo(tester.getSize(when).width, 0.01), reason: 'drawn at its own size');
  });

  testWidgets('a long folder name ends in an ellipsis instead of pushing the time off the line', (tester) async {
    final folder = Folder(
      id: 'f1',
      name: 'Client meetings and weekly reviews with the whole team',
      color: '#6B7280',
      icon: 'folder',
      createdAt: DateTime(2026),
      updatedAt: DateTime(2026),
      order: 0,
      isDefault: false,
      isSystem: false,
      conversationCount: 1,
    );
    await pumpHeader(tester, width: 375, folder: folder);
    expectOneLine(tester, 375);
    // The chip stops at its share of the line (the header's gutters, then the folder's share)...
    const cap = (375 - 2 * OmiSpacing.md) * ConversationDetailHeader.labelShare;
    expect(tester.getSize(find.byKey(const Key('conversation_folder'))).width, closeTo(cap, 0.5));
    // ...and its label is cut there with an ellipsis, not clipped.
    final label = tester.renderObject<RenderParagraph>(
        find.descendant(of: find.byKey(const Key('conversation_folder')), matching: find.text(folder.name)));
    expect(label.didExceedMaxLines, isTrue);
    expect(label.overflow, TextOverflow.ellipsis);
  });
}
