import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_header.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';
import 'package:omi/ui/ui.dart';

void main() {
  testWidgets('detail title hugs one line and stays centred beside emoji at two lines', (tester) async {
    tester.view.physicalSize = const Size(390, 844);
    tester.view.devicePixelRatio = 1;
    addTearDown(tester.view.reset);

    final conversation = ServerConversation(
      id: 'title-alignment',
      createdAt: DateTime(2026, 9, 28, 12),
      structured: Structured('Short title', '', emoji: '🧠'),
    );
    final detail = ConversationDetailProvider()
      ..selectedDate = conversationLocalDayKey(conversation.createdAt)
      ..setCachedConversation(conversation)
      ..titleController = TextEditingController(text: conversation.structured.title)
      ..titleFocusNode = FocusNode();
    final folders = FolderProvider(foldersFetcher: () async => []);
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
          home: Scaffold(body: ConversationDetailHeader(onOpenRecordings: (_) {})),
        ),
      ),
    );

    final titleField = find.byType(ConversationTitleField);
    final emoji = find.text('🧠');
    const lineHeight = 20.0 * 1.25; // OmiType.title3 with the header's line height.

    void expectCentred(double expectedHeight) {
      expect(tester.getSize(titleField).height, closeTo(expectedHeight, 1));
      expect((tester.getCenter(titleField).dy - tester.getCenter(emoji).dy).abs(), lessThan(1));
    }

    expectCentred(lineHeight);

    detail.titleController!.text = 'First line\nSecond line';
    await tester.pump();
    expectCentred(lineHeight * 2);
  });
}
