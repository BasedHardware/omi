import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/conversations/widgets/folder_options_sheet.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/folder_provider.dart';

/// Answers the delete as the server would; what the sheet then does to Home is under test.
class _ServerDeleteFolderProvider extends FolderProvider {
  _ServerDeleteFolderProvider(List<Folder> folders) : super(foldersFetcher: () async => folders);

  final deletes = <(String, String?)>[];

  @override
  Future<bool> deleteFolder(String folderId, {String? moveToFolderId}) async {
    deletes.add((folderId, moveToFolderId));
    return true;
  }
}

Folder _folder(String id, String name, {required int order}) => Folder(
      id: id,
      name: name,
      color: '#FFFFFF',
      icon: 'folder',
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      order: order,
      isDefault: false,
      isSystem: false,
      conversationCount: 1,
    );

ServerConversation _conversation(String id, {String? folderId, required DateTime createdAt}) => ServerConversation(
      id: id,
      createdAt: createdAt,
      structured: Structured('Title', 'Overview'),
      status: ConversationStatus.completed,
      folderId: folderId,
    );

void main() {
  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  // Folders are edited from search's folder tiles and Home has no folder chip, so a folder filter
  // left on Home by a delete hid every other conversation with nothing to clear it.
  testWidgets('deleting a folder reloads Home without filtering it to the destination folder', (tester) async {
    final work = _folder('work', 'Work', order: 0);
    final folders = _ServerDeleteFolderProvider([work, _folder('archive', 'Archive', order: 1)]);
    addTearDown(folders.dispose);
    await folders.loadFolders();

    var serverRows = [
      _conversation('filed', folderId: 'work', createdAt: DateTime(2026, 10, 1, 9)),
      _conversation('unfiled', createdAt: DateTime(2026, 10, 1, 8)),
    ];
    var listFetches = 0;
    final conversations = ConversationProvider(
      conversationListFetcher: () async {
        listFetches++;
        return (items: serverRows, ok: true);
      },
      isSignedIn: () => true,
    );
    addTearDown(conversations.dispose);
    await conversations.fetchConversations();
    expect(conversations.displayedConversations.map((c) => c.id), ['filed', 'unfiled']);

    await tester.pumpWidget(MultiProvider(
      providers: [
        ChangeNotifierProvider<FolderProvider>.value(value: folders),
        ChangeNotifierProvider<ConversationProvider>.value(value: conversations),
      ],
      child: MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        home: Scaffold(
          body: Builder(
            builder: (context) => TextButton(
              onPressed: () => showFolderOptions(context, work),
              child: const Text('Open folder options'),
            ),
          ),
        ),
      ),
    ));

    await tester.tap(find.text('Open folder options'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Delete Folder'));
    await tester.pumpAndSettle();

    // The server moves Work's conversations into Archive.
    serverRows = [
      _conversation('filed', folderId: 'archive', createdAt: DateTime(2026, 10, 1, 9)),
      _conversation('unfiled', createdAt: DateTime(2026, 10, 1, 8)),
    ];
    await tester.tap(find.text('Archive'));
    await tester.pumpAndSettle();

    expect(folders.deletes, [('work', 'archive')]);
    expect(conversations.selectedFolderId, isNull, reason: 'Home has no folder chip to clear a folder filter');
    expect(conversations.displayedConversations.map((c) => c.id), ['filed', 'unfiled']);
    expect(listFetches, 2, reason: 'Home reloads after the delete');
    expect(conversations.displayedConversations.first.folderId, 'archive');

    await tester.pumpWidget(const SizedBox.shrink());
  });
}
