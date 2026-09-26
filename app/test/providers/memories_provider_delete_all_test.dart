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

final _memory = Memory(
  id: 'server-memory',
  uid: 'memory-delete-all-test-user',
  content: 'Still stored on the server',
  category: MemoryCategory.manual,
  createdAt: DateTime(2026, 1, 1),
  updatedAt: DateTime(2026, 1, 1),
  visibility: MemoryVisibility.private,
);

MemoriesProvider _provider() => MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        return GetMemoriesResult([_memory], true);
      },
    );

void main() {
  setUpAll(() {
    Env.init(_UnreachableApiEnv());
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'memory-delete-all-test-user'});
    await SharedPreferencesUtil.init();
  });

  test('a clear-all the server did not accept keeps the memories', () async {
    TestWidgetsFlutterBinding.ensureInitialized();
    final provider = _provider();
    addTearDown(provider.dispose);
    await provider.loadMemories();

    final cleared = await provider.deleteAllMemories();

    expect(cleared, isFalse);
    expect(provider.memories.map((m) => m.id), [_memory.id]);
  });

  testWidgets('the sheet does not say memory was cleared when the server rejected it', (tester) async {
    tester.view.physicalSize = const Size(1200, 2400);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.reset);
    final provider = _provider();
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
    await tester.tap(find.text('Delete All Memories'));
    await tester.pumpAndSettle();

    await tester.runAsync(() async {
      await tester.tap(find.text('Clear Memory'));
      await Future<void>.delayed(const Duration(milliseconds: 300));
    });
    await tester.pumpAndSettle();

    expect(provider.memories.map((m) => m.id), [_memory.id]);
    expect(find.text("Omi's memory about you has been cleared"), findsNothing);
    expect(find.text('Something went wrong! Please try again later.'), findsOneWidget);

    await tester.pumpAndSettle(const Duration(seconds: 3));
  });
}
