import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/memories/widgets/memory_management_sheet.dart';
import 'package:omi/providers/memories_provider.dart';

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
    SharedPreferences.setMockInitialValues({'uid': 'memory-visibility-test-user'});
    await SharedPreferencesUtil.init();
  });

  Memory publicMemory(String id) => Memory(
        id: id,
        uid: 'memory-visibility-test-user',
        content: 'Memory $id',
        category: MemoryCategory.manual,
        createdAt: DateTime(2026, 1, 1),
        updatedAt: DateTime(2026, 1, 1),
        visibility: MemoryVisibility.public,
      );

  test('making all memories private keeps them public when the server rejects it', () async {
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        return GetMemoriesResult([publicMemory('a'), publicMemory('b')], true);
      },
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    final updated = await provider.updateAllMemoriesVisibility(true);

    expect(updated, isFalse);
    expect(provider.memories.map((memory) => memory.visibility), everyElement(MemoryVisibility.public));
  });

  test('making one memory private keeps it public when the server rejects it', () async {
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        return GetMemoriesResult([publicMemory('a')], true);
      },
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();

    await provider.updateMemoryVisibility(provider.memories.single, MemoryVisibility.private);

    expect(provider.memories.single.visibility, MemoryVisibility.public);
  });

  testWidgets('the sheet does not say all memories are private when the change failed', (tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        return GetMemoriesResult([publicMemory('a')], true);
      },
    );
    addTearDown(provider.dispose);
    await tester.runAsync(provider.loadMemories);

    await tester.pumpWidget(
      ChangeNotifierProvider<MemoriesProvider>.value(
        value: provider,
        child: MaterialApp(
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: Builder(
              builder: (context) => TextButton(
                onPressed: () => showModalBottomSheet(
                  context: context,
                  isScrollControlled: true,
                  builder: (_) => MemoryManagementSheet(provider: provider),
                ),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
    );
    await tester.tap(find.text('open'));
    await tester.pumpAndSettle();

    await tester.runAsync(() async {
      await tester.tap(find.text('Make All Memories Private'));
      await Future<void>.delayed(const Duration(milliseconds: 200));
    });
    await tester.pump();

    expect(find.text('All memories are now private'), findsNothing);
    expect(find.text('Something went wrong! Please try again later.'), findsOneWidget);

    await tester.pumpAndSettle(const Duration(seconds: 3));
  });
}
