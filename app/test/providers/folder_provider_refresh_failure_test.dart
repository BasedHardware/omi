import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/folders.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/folder.dart';
import 'package:omi/env/env.dart';
import 'package:omi/providers/folder_provider.dart';

class _UnreachableApiEnv implements EnvFields {
  @override
  String? get apiBaseUrl => 'http://127.0.0.1:1/';

  @override
  dynamic noSuchMethod(Invocation invocation) => null;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUpAll(() {
    Env.init(_UnreachableApiEnv());
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  test('a failed folder refresh keeps the folders already loaded', () async {
    var calls = 0;
    final provider = FolderProvider(
      foldersFetcher: () async => calls++ == 0 ? [_folder('work')] : await getFolders(),
    );
    addTearDown(provider.dispose);

    await provider.loadFolders();
    await provider.loadFolders();

    expect(calls, 2);
    expect(provider.folders.map((folder) => folder.id), ['work']);
    expect(provider.error, isNotNull);
    expect(provider.isLoading, isFalse);
  });
}

Folder _folder(String id) => Folder(
      id: id,
      name: 'Work',
      color: '#FFFFFF',
      icon: 'folder',
      createdAt: DateTime.utc(2026),
      updatedAt: DateTime.utc(2026),
      order: 0,
      isDefault: false,
      isSystem: false,
      conversationCount: 3,
    );
