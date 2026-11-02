import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

const _coffee = 'Coffee with Sam on Friday';
const _gym = 'Gym at 7am';

Memory _memory(String id, String content) => Memory(
      id: id,
      uid: 'memories-search-user',
      content: content,
      category: MemoryCategory.manual,
      createdAt: DateTime(2026, 10, 1),
      updatedAt: DateTime(2026, 10, 1),
      visibility: MemoryVisibility.private,
    );

MemoriesProvider _memoriesProvider() => MemoriesProvider(
      fetchMemoriesRequest: ({int limit = 100, int offset = 0, bool thisDeviceOnly = false}) async =>
          GetMemoriesResult([_memory('mem-coffee', _coffee), _memory('mem-gym', _gym)], true),
    );

/// The providers sit above the navigator, as in main.dart, so they outlive every Memories page
/// pushed on top of it.
Future<NavigatorState> _pumpApp(WidgetTester tester, MemoriesProvider memories) async {
  final home = HomeProvider();
  addTearDown(home.dispose);
  final navigatorKey = GlobalKey<NavigatorState>();
  await tester.pumpWidget(
    MultiProvider(
      providers: [
        ChangeNotifierProvider<MemoriesProvider>.value(value: memories),
        ChangeNotifierProvider<HomeProvider>.value(value: home),
      ],
      child: MaterialApp(
        navigatorKey: navigatorKey,
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: const SizedBox.shrink(),
      ),
    ),
  );
  return navigatorKey.currentState!;
}

Future<void> _openMemories(WidgetTester tester, NavigatorState navigator) async {
  unawaited(navigator.push(MaterialPageRoute<void>(builder: (_) => const MemoriesPage(showMindMap: false))));
  await tester.pumpAndSettle();
}

Finder get _searchField => find.descendant(of: find.byType(OmiSearchField), matching: find.byType(TextField));

String _searchText(WidgetTester tester) => tester.widget<TextField>(_searchField).controller!.text;

Finder get _clearSearchButton => find.byTooltip(lookupAppLocalizations(const Locale('en')).clearSearch);

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  testWidgets('a search still filtering Memories is shown in the field when you come back', (tester) async {
    final memories = _memoriesProvider();
    addTearDown(memories.dispose);
    final navigator = await _pumpApp(tester, memories);

    await _openMemories(tester, navigator);
    await tester.enterText(_searchField, 'Coffee');
    await tester.pump();
    expect(find.text(_coffee), findsOneWidget);
    expect(find.text(_gym), findsNothing);

    // Leave with the search in place, then open Memories again.
    await tester.tap(find.byType(OmiBackButton));
    await tester.pumpAndSettle();
    expect(find.byType(MemoriesPage), findsNothing);
    await _openMemories(tester, navigator);

    // The list is still filtered by the search, so the field shows it as typed, with its clear button.
    expect(_searchText(tester), 'Coffee');
    expect(find.text(_coffee), findsOneWidget);
    expect(find.text(_gym), findsNothing);

    await tester.tap(_clearSearchButton);
    await tester.pump();
    expect(_searchText(tester), isEmpty);
    expect(memories.searchQuery, isEmpty);
    expect(find.text(_coffee), findsOneWidget);
    expect(find.text(_gym), findsOneWidget);
  });

  testWidgets('Memories opened from a Global Search result shows that search in the field', (tester) async {
    final memories = _memoriesProvider();
    addTearDown(memories.dispose);
    final navigator = await _pumpApp(tester, memories);

    // Global Search sets the query on the shared provider, then opens the page.
    memories.setSearchQuery('coffee');
    await _openMemories(tester, navigator);

    expect(_searchText(tester), 'coffee');
    expect(find.text(_coffee), findsOneWidget);
    expect(find.text(_gym), findsNothing);
    expect(_clearSearchButton, findsOneWidget);
  });
}
