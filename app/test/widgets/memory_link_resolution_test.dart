import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/chat/widgets/content_blocks/memory_link_block.dart';
import 'package:omi/pages/memories/widgets/memory_edit_sheet.dart';
import 'package:omi/providers/memories_provider.dart';

Memory _memory() => Memory(
      id: 'new-memory',
      uid: 'memory-link-user',
      content: 'A newly saved memory',
      category: MemoryCategory.manual,
      createdAt: DateTime.utc(2026, 10, 26),
      updatedAt: DateTime.utc(2026, 10, 26),
      visibility: MemoryVisibility.private,
    );

const _block = MemoryLinkContentBlock(
  id: 'saved-memory',
  memoryId: 'new-memory',
  summary: 'A newly saved memory',
);
const _open = Key('chat-block-memoryLink-saved-memory-open');
const _retry = Key('chat-block-memoryLink-saved-memory-retry');

Future<void> _pump(WidgetTester tester, MemoriesProvider provider) async {
  await tester.pumpWidget(ChangeNotifierProvider.value(
    value: provider,
    child: MaterialApp(
      theme: ThemeData.dark(),
      localizationsDelegates: AppLocalizations.localizationsDelegates,
      supportedLocales: AppLocalizations.supportedLocales,
      home: const Scaffold(body: MemoryLinkBlock(block: _block)),
    ),
  ));
  await tester.pump();
  await tester.pump();
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({'uid': 'memory-link-user'});
    await SharedPreferencesUtil.init();
  });

  testWidgets('a newly saved chat memory refreshes an already loaded list and opens', (tester) async {
    var fetches = 0;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult(++fetches == 1 ? [] : [_memory()], true),
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();
    await _pump(tester, provider);

    expect(fetches, 2);
    expect(find.text('No longer available'), findsNothing);
    expect(find.byKey(_open), findsOneWidget);
    await tester.tap(find.byKey(_open));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 350));
    expect(find.byType(MemoryEditSheet), findsOneWidget);
    expect(tester.widget<MemoryEditSheet>(find.byType(MemoryEditSheet)).memory.id, 'new-memory');
    expect(find.text('A newly saved memory'), findsWidgets);
  });

  testWidgets('a loaded matching memory opens without another collection fetch', (tester) async {
    var fetches = 0;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        fetches++;
        return GetMemoriesResult([_memory()], true);
      },
    );
    addTearDown(provider.dispose);
    await provider.loadMemories();
    await _pump(tester, provider);

    expect(fetches, 1);
    expect(find.byKey(_open), findsOneWidget);
  });

  testWidgets('a failed memory read offers an explicit retry without claiming deletion', (tester) async {
    var fetches = 0;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        fetches++;
        return fetches == 1
            ? const GetMemoriesResult([], true, statusCode: 503, failureReason: MemoriesFetchFailureReason.httpError)
            : GetMemoriesResult([_memory()], true);
      },
    );
    addTearDown(provider.dispose);
    await _pump(tester, provider);

    expect(find.text('No longer available'), findsNothing);
    expect(find.byKey(_retry), findsOneWidget);
    await tester.tap(find.byKey(_retry));
    await tester.pump();
    await tester.pump();
    expect(fetches, 2);
    expect(find.byKey(_open), findsOneWidget);
  });

  testWidgets('a bounded list miss stays unresolved and does not automatically poll', (tester) async {
    var fetches = 0;
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async {
        fetches++;
        return const GetMemoriesResult([], true, truncated: true);
      },
    );
    addTearDown(provider.dispose);
    await _pump(tester, provider);

    expect(find.text('No longer available'), findsNothing);
    expect(find.byKey(_retry), findsOneWidget);
    final settledFetches = fetches;
    await tester.pump(const Duration(seconds: 10));
    expect(fetches, settledFetches);
  });

  testWidgets('clearing the account during hydration cannot publish the old memory', (tester) async {
    final response = Completer<GetMemoriesResult>();
    final provider = MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) => response.future,
    );
    addTearDown(provider.dispose);
    await _pump(tester, provider);
    provider.clearUserData();
    response.complete(GetMemoriesResult([_memory()], true));
    await tester.pump();
    await tester.pump();

    expect(provider.memories, isEmpty);
    expect(find.text('No longer available'), findsNothing);
    expect(find.byKey(_retry), findsOneWidget);
  });
}
