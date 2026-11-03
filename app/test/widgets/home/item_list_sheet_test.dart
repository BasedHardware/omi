import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/memories.dart' show GetMemoriesResult;
import 'package:omi/backend/schema/action_item.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/home/home_deep_links.dart';
import 'package:omi/pages/home/item_list_sheet.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/ui/ui.dart';
import '../../helpers/sfpro_font_fixtures.dart';

/// h.omi.me/items: an ordered list of conversations, tasks and memories that opens as one sheet
/// over Home (contract M, Mobile).
void main() {
  final t0 = DateTime.utc(2026, 10, 12, 9);

  ServerConversation conversation(String id, String title) => ServerConversation(
        id: id,
        createdAt: t0,
        startedAt: t0,
        finishedAt: t0.add(const Duration(minutes: 20)),
        structured: Structured(title, ''),
        source: ConversationSource.omi,
      );

  Memory memory(String id, String content) => Memory(
        id: id,
        uid: 'owner',
        content: content,
        category: MemoryCategory.manual,
        createdAt: t0,
        updatedAt: t0,
        visibility: MemoryVisibility.private,
      );

  group('parsing', () {
    test('keeps URL order across kinds and drops unknown keys, empty ids and repeats', () {
      expect(
        HomeDeepLink.parseItemList(
            'task=t-1&utm_source=x&conversation=c-1&memory=m-1&conversation=&task=t-1&memory=m-2'),
        [
          (kind: 'task', id: 't-1'),
          (kind: 'conversation', id: 'c-1'),
          (kind: 'memory', id: 'm-1'),
          (kind: 'memory', id: 'm-2'),
        ],
      );
    });

    test('stops at ten items', () {
      final query = List.generate(12, (i) => 'task=t-$i').join('&');
      final items = HomeDeepLink.parseItemList(query);
      expect(items, hasLength(HomeDeepLink.maxListItems));
      expect(items.last.id, 't-9');
    });

    test('decodes percent-encoded ids and ignores malformed pairs', () {
      expect(
        HomeDeepLink.parseItemList('conversation=a%2Db&%zz=1&memory=%E0&task&conversation=a%2Fb'),
        [(kind: 'conversation', id: 'a-b')],
      );
      // Slashes and `..` must not survive into the conversation URL path.
      expect(
        HomeDeepLink.parseItemList('conversation=..%2F..%2Fusers&task=%3Cscript%3E&memory=m-1'),
        [(kind: 'memory', id: 'm-1')],
      );
    });

    test('h.omi.me/items routes into Home with only the recognised pairs', () {
      expect(
        HomeDeepLink.itemRouteFromAppLink(Uri.parse('https://h.omi.me/items?conversation=c-1&x=y&task=t-1&memory=m-1')),
        '/items?conversation=c-1&task=t-1&memory=m-1',
      );
      // The web fallback's iOS button.
      expect(
        HomeDeepLink.itemRouteFromAppLink(Uri.parse('omi://h.omi.me/items?memory=m-1&task=t-1')),
        '/items?memory=m-1&task=t-1',
      );
      expect(HomeDeepLink.itemRouteFromAppLink(Uri.parse('https://h.omi.me/items?foo=bar')), '/items');
      expect(
        HomeDeepLink.itemRouteFromAppLink(Uri.parse('https://h.omi.me/items?conversation=..%2F..%2Fx&task=t-1')),
        '/items?task=t-1',
      );
      for (final raw in [
        'https://evil.example/items?task=t-1',
        'http://h.omi.me/items?task=t-1',
        'https://h.omi.me/items/extra?task=t-1',
      ]) {
        expect(HomeDeepLink.itemRouteFromAppLink(Uri.parse(raw)), isNull, reason: raw);
      }
    });

    test('the Home route keeps the order and shows Home behind the sheet', () {
      final link = HomeDeepLink.parse('/items?memory=m-1&conversation=c-1')!;
      expect(link.alias, 'items');
      expect(link.itemList, [(kind: 'memory', id: 'm-1'), (kind: 'conversation', id: 'c-1')]);
      expect(link.tabIndex, HomeProvider.homeTab);
    });
  });

  test('memories resolve in one owner-wide walk that stops once all are found', () async {
    final pages = <int>[];
    final found = await resolveIndexedMemoriesByIds(
      {'m-1', 'm-3'},
      uid: 'owner',
      ownerIsCurrent: () => true,
      fetchPage: ({required int limit, required int offset, String? cursor}) async {
        pages.add(offset);
        final rows = offset == 0
            ? [memory('m-1', 'one'), ...List.generate(limit - 1, (i) => memory('x-$i', 'x'))]
            : [memory('m-3', 'three')];
        return GetMemoriesResult(rows, true);
      },
    );
    expect(found.keys, unorderedEquals(['m-1', 'm-3']));
    expect(pages, [0, 500]);
  });

  group('sheet', () {
    Future<void> pumpSheet(
      WidgetTester tester,
      List<ItemLinkRef> items,
      ItemListLoader loader, {
      ItemListOpener? onOpen,
    }) async {
      await tester.pumpWidget(MaterialApp(
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        theme: buildOmiTheme(brightness: Brightness.dark),
        home: Scaffold(
          body: ItemListSheet(items: items, loader: loader, onOpen: onOpen ?? (_, __) {}),
        ),
      ));
    }

    testWidgets('lists items in link order, with unavailable rows muted in place', (tester) async {
      final opened = <String>[];
      await pumpSheet(
        tester,
        const [
          (kind: 'task', id: 't-1'),
          (kind: 'conversation', id: 'gone'),
          (kind: 'memory', id: 'm-1'),
          (kind: 'conversation', id: 'c-1'),
          (kind: 'task', id: 'cancelled'),
        ],
        ItemListLoader(
          conversationById: (id) async => id == 'c-1' ? conversation('c-1', 'Pricing sync') : null,
          taskById: (id) async => switch (id) {
            't-1' => const ActionItemWithMetadata(id: 't-1', description: 'Send the deck', completed: false),
            _ =>
              const ActionItemWithMetadata(id: 'cancelled', description: 'Old', completed: false, status: 'cancelled'),
          },
          memoriesByIds: (ids) async => {'m-1': memory('m-1', 'Prefers window seats')},
        ),
        onOpen: (_, entry) => opened.add('${entry.ref.kind}:${entry.ref.id}'),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('item-list-row-0')), findsOneWidget);
      expect(find.byKey(const Key('item-list-unavailable-1')), findsOneWidget);
      expect(find.byKey(const Key('item-list-row-2')), findsOneWidget);
      expect(find.byKey(const Key('item-list-row-3')), findsOneWidget);
      expect(find.byKey(const Key('item-list-unavailable-4')), findsOneWidget);
      expect(find.text('No longer available'), findsNWidgets(2));
      final top = [
        'Send the deck',
        'Prefers window seats',
        'Pricing sync',
      ].map((t) => tester.getTopLeft(find.text(t)).dy).toList();
      expect(top, orderedEquals([...top]..sort()));

      await tester.tap(find.text('Pricing sync'));
      await tester.tap(find.text('No longer available').first);
      await tester.tap(find.text('Send the deck'));
      expect(opened, ['conversation:c-1', 'task:t-1']);
    });

    testWidgets('a row loads on its own and a failed lookup reads as unavailable', (tester) async {
      final slowMemory = Completer<Map<String, Memory>>();
      await pumpSheet(
        tester,
        const [(kind: 'conversation', id: 'c-1'), (kind: 'memory', id: 'm-1'), (kind: 'task', id: 'boom')],
        ItemListLoader(
          conversationById: (id) async => conversation(id, 'Standup'),
          taskById: (_) async => throw Exception('network'),
          memoriesByIds: (_) => slowMemory.future,
        ),
      );
      await tester.pump();
      expect(find.text('Standup'), findsOneWidget);
      expect(find.byKey(const Key('item-list-loading-1')), findsOneWidget);
      expect(find.byKey(const Key('item-list-unavailable-2')), findsOneWidget);

      slowMemory.complete(const {});
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('item-list-unavailable-1')), findsOneWidget);
    });

    testWidgets('a link with no items shows the empty state', (tester) async {
      await pumpSheet(tester, const [], const ItemListLoader());
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('item-list-empty')), findsOneWidget);
      expect(find.text('No Items'), findsOneWidget);
    });

    testWidgets('the /items route opens the sheet titled with the count', (tester) async {
      final home = HomeProvider();
      addTearDown(home.dispose);
      await tester.pumpWidget(ChangeNotifierProvider<HomeProvider>.value(
        value: home,
        child: MaterialApp(
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          theme: buildOmiTheme(brightness: Brightness.dark),
          home: const Scaffold(body: SizedBox(key: Key('items-link-home'))),
        ),
      ));
      final context = tester.element(find.byKey(const Key('items-link-home')));
      unawaited(showItemListSheet(
        context,
        HomeDeepLink.parse('/items?conversation=c-1&task=t-1')!.itemList,
        loader: ItemListLoader(
          conversationById: (id) async => conversation(id, 'Pricing sync'),
          taskById: (id) async =>
              const ActionItemWithMetadata(id: 't-1', description: 'Send the deck', completed: true),
        ),
      ));
      await tester.pumpAndSettle();
      expect(find.text('2 Items'), findsOneWidget);
      expect(find.text('Pricing sync'), findsOneWidget);
      expect(find.text('Send the deck'), findsOneWidget);
    });
  });

  for (final brightness in Brightness.values) {
    testWidgets('item list renders in ${brightness.name}', (tester) async {
      debugDefaultTargetPlatformOverride = TargetPlatform.iOS;
      tester.view.physicalSize = const Size(393, 760);
      tester.view.devicePixelRatio = 1;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);
      final previousPalette = OmiColors.active;
      OmiColors.active = brightness == Brightness.dark ? OmiPalette.dark : OmiPalette.light;
      addTearDown(() => OmiColors.active = previousPalette);
      final base = buildOmiTheme(brightness: brightness);
      final theme = base.copyWith(
        platform: TargetPlatform.iOS,
        textTheme: base.textTheme.apply(fontFamily: 'SF Pro Display'),
      );

      const evidence = String.fromEnvironment('OMI_ITEM_LIST_UI_EVIDENCE_DIR');
      if (evidence.isNotEmpty) {
        await tester.runAsync(() async {
          final fonts = jsonDecode(await rootBundle.loadString('FontManifest.json')) as List<dynamic>;
          for (final entry in fonts) {
            final loader = FontLoader(entry['family'] as String);
            for (final font in entry['fonts'] as List<dynamic>) {
              loader.addFont(rootBundle.load(font['asset'] as String));
            }
            await loader.load();
          }
          for (final family in const [
            'Roboto',
            'CupertinoSystemText',
            'CupertinoSystemDisplay',
            '.SF UI Text',
            '.SF UI Display',
            'SF Pro Display',
            'FlutterTest'
          ]) {
            final loader = FontLoader(family)
              ..addFont(sfProFont('SFPRODISPLAYMEDIUM.OTF'))
              ..addFont(sfProFont('SFPRODISPLAYREGULAR.OTF'));
            await loader.load();
          }
        });
      }

      const boundaryKey = ValueKey('item-list-evidence');
      await tester.pumpWidget(RepaintBoundary(
        key: boundaryKey,
        child: MaterialApp(
          locale: const Locale('en'),
          localizationsDelegates: AppLocalizations.localizationsDelegates,
          supportedLocales: AppLocalizations.supportedLocales,
          theme: theme,
          debugShowCheckedModeBanner: false,
          home: Scaffold(
            body: Builder(
              builder: (context) => Center(
                child: TextButton(
                  key: const Key('open-items'),
                  onPressed: () => showItemListSheet(
                    context,
                    HomeDeepLink.parse(
                      '/items?conversation=c-1&task=t-1&memory=m-1&task=t-2&conversation=gone',
                    )!
                        .itemList,
                    loader: ItemListLoader(
                      conversationById: (id) async => id == 'c-1' ? conversation(id, 'Pricing sync with Priya') : null,
                      taskById: (id) async => id == 't-1'
                          ? const ActionItemWithMetadata(
                              id: 't-1', description: 'Send the Q4 deck to Priya', completed: false)
                          : const ActionItemWithMetadata(
                              id: 't-2', description: 'Book flights to Lisbon', completed: true),
                      memoriesByIds: (ids) async => {'m-1': memory('m-1', 'Prefers window seats on long flights')},
                    ),
                    onOpen: (_, __) {},
                  ),
                  child: const Text('Home'),
                ),
              ),
            ),
          ),
        ),
      ));
      await tester.tap(find.byKey(const Key('open-items')));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      expect(find.text('5 Items'), findsOneWidget);
      expect(find.text('No longer available'), findsOneWidget);

      if (evidence.isNotEmpty) {
        await tester.runAsync(() async {
          final boundary = tester.renderObject<RenderRepaintBoundary>(find.byKey(boundaryKey));
          final image = await boundary.toImage(pixelRatio: 3);
          final bytes = await image.toByteData(format: ui.ImageByteFormat.png);
          final dir = await Directory(evidence).create(recursive: true);
          await File('${dir.path}/item-list-${brightness.name}.png').writeAsBytes(bytes!.buffer.asUint8List());
          image.dispose();
        });
      }
      await tester.pumpWidget(const SizedBox.shrink());
      debugDefaultTargetPlatformOverride = null;
    });
  }
}
