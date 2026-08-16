import 'dart:async';

import 'package:flutter_test/flutter_test.dart';

import 'package:omi/backend/schema/folder.dart';
import 'package:omi/providers/folder_provider.dart';

void main() {
  test('clearUserData invalidates an older in-flight folder load', () async {
    final response = Completer<List<Folder>>();
    final provider = FolderProvider(foldersFetcher: () => response.future);
    addTearDown(provider.dispose);

    final load = provider.loadFolders();
    provider.clearUserData();
    response.complete([_folder('old-account')]);
    await load;

    expect(provider.folders, isEmpty);
    expect(provider.isLoading, isFalse);
    expect(provider.error, isNull);
  });
}

Folder _folder(String id) => Folder(
      id: id,
      name: 'Old account',
      color: '#FFFFFF',
      icon: 'folder',
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      order: 0,
      isDefault: false,
      isSystem: false,
      conversationCount: 1,
    );
