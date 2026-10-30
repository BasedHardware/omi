import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/http/api/knowledge_graph_api.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/utils/platform/platform_manager.dart';

Future<Map<String, dynamic>> _emptyGraph() async => {'nodes': [], 'edges': []};

Future<Map<String, dynamic>> _neverLoads() => Completer<Map<String, dynamic>>().future;

Widget _app(Widget home) {
  return MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: MediaQuery(
      data: const MediaQueryData(size: Size(414, 896), padding: EdgeInsets.only(top: 47, bottom: 34)),
      child: home,
    ),
  );
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    PlatformManager.initializeForLocalHarness();
  });

  group('user node label', () {
    test('falls back to the localized "You", not English "Me"', () {
      expect(memoryGraphUserLabel('', lookupAppLocalizations(const Locale('es'))), 'Tú');
      expect(memoryGraphUserLabel('  ', lookupAppLocalizations(const Locale('de'))), 'Sie');
      expect(memoryGraphUserLabel('', lookupAppLocalizations(const Locale('en'))), 'You');
    });

    test('uses the given name when one is set', () {
      expect(memoryGraphUserLabel(' Ana ', lookupAppLocalizations(const Locale('es'))), 'Ana');
    });
  });

  testWidgets('full-page empty state sits below the app bar and wraps its message', (tester) async {
    await tester.binding.setSurfaceSize(const Size(414, 896));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    await tester.pumpWidget(_app(const MemoryGraphPage(trackOpenEvent: false, loadGraph: _emptyGraph)));
    await tester.pumpAndSettle();

    final l10n = AppLocalizations.of(tester.element(find.byType(MemoryGraphPage)));
    final appBarBottom = tester.getBottomLeft(find.byType(AppBar)).dy;
    final title = find.text(l10n.noKnowledgeGraphYet);
    final message = find.text(l10n.knowledgeGraphWillBuildAutomatically);

    expect(tester.getTopLeft(title).dy, greaterThanOrEqualTo(appBarBottom));
    expect(tester.getSize(message).height, greaterThan(tester.getSize(title).height));
    expect(tester.getRect(message).width, lessThan(414));
  });

  testWidgets('embedded empty state wraps its message inside the card', (tester) async {
    await tester.pumpWidget(
      _app(
        const Scaffold(
          body: Center(
            child: SizedBox(
              width: 360,
              height: 180,
              child: MemoryGraphPage(
                embedded: true,
                showAppBar: false,
                showShareButton: false,
                trackOpenEvent: false,
                loadGraph: _emptyGraph,
              ),
            ),
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    final l10n = AppLocalizations.of(tester.element(find.byType(MemoryGraphPage)));
    final card = tester.getRect(find.byType(MemoryGraphPage));
    final message = find.text(l10n.knowledgeGraphWillBuildAutomatically);
    final messageRect = tester.getRect(message);

    expect(card.contains(messageRect.topLeft) && card.contains(messageRect.bottomRight), isTrue);
    expect(tester.getSize(message).height, greaterThan(tester.getSize(find.text(l10n.noKnowledgeGraphYet)).height));
  });

  testWidgets('preview shows a compact skeleton while loading', (tester) async {
    await tester.pumpWidget(
      _app(
        const Scaffold(
          body: MemoryGraphPage(embedded: true, preview: true, trackOpenEvent: false, loadGraph: _neverLoads),
        ),
      ),
    );
    await tester.pump();

    expect(find.byKey(const ValueKey('memories_mind_map_loading')), findsOneWidget);
    expect(tester.getSize(find.byKey(const ValueKey('memories_mind_map_preview'))).height, lessThan(170));
    final l10n = AppLocalizations.of(tester.element(find.byType(MemoryGraphPage)));
    expect(find.text(l10n.loadingKnowledgeGraph), findsNothing);
  });

  testWidgets('preview failure collapses to one row whose Try Again reloads', (tester) async {
    var calls = 0;
    Future<Map<String, dynamic>> load() async {
      calls++;
      if (calls == 1) throw Exception('offline');
      return {'nodes': [], 'edges': []};
    }

    await tester.pumpWidget(
      _app(Scaffold(body: MemoryGraphPage(embedded: true, preview: true, trackOpenEvent: false, loadGraph: load))),
    );
    await tester.pumpAndSettle();

    final l10n = AppLocalizations.of(tester.element(find.byType(MemoryGraphPage)));
    final row = find.byKey(const ValueKey('memories_mind_map_error'));
    expect(row, findsOneWidget);
    expect(find.text(l10n.couldNotLoadKnowledgeGraph), findsOneWidget);
    expect(tester.getSize(row).height, lessThan(80));

    await tester.tap(find.byKey(const ValueKey('memories_mind_map_retry')));
    await tester.pumpAndSettle();
    expect(calls, 2);
    expect(row, findsNothing);
    expect(find.byKey(const ValueKey('memories_mind_map_preview')), findsOneWidget);
  });

  testWidgets('saved memories without assertions are readable and can load later graph pages', (tester) async {
    await tester.pumpWidget(_app(MemoryGraphPage(
      trackOpenEvent: false,
      loadGraph: () async => {
        'nodes': [],
        'edges': [],
        'catalog_nodes': [
          {'id': 'memory:1', 'label': 'I enjoy hiking'}
        ],
        'has_more': true,
        'next_cursor': 'signed-page-2',
      },
      loadMoreGraph: (cursor) async {
        expect(cursor, 'signed-page-2');
        return {
          'nodes': [
            {'id': 'hiking', 'label': 'Hiking', 'node_type': 'concept'}
          ],
          'edges': [],
          'has_more': false
        };
      },
    )));
    await tester.pumpAndSettle();
    expect(find.text('I enjoy hiking'), findsOneWidget);
    expect(find.byKey(const ValueKey('mind_map_memory_catalog')), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('mind_map_load_more')));
    await tester.pumpAndSettle();
    final state = tester.state<MemoryGraphPageState>(find.byType(MemoryGraphPage));
    expect(state.simulation.nodes.any((n) => n.id == 'hiking'), true);
    expect(state.hasFittedBounds, true);
    expect(state.simulation.edges, isEmpty);
    expect(find.byKey(const ValueKey('mind_map_load_more')), findsNothing);
  });

  testWidgets('failed refresh preserves readable catalog and offers retry', (tester) async {
    var calls = 0;
    await tester.pumpWidget(_app(MemoryGraphPage(
        trackOpenEvent: false,
        loadGraph: () async {
          if (++calls > 1) throw Exception('offline');
          return {
            'nodes': [],
            'edges': [],
            'catalog_nodes': [
              {'id': 'memory:1', 'label': 'Saved memory'}
            ]
          };
        })));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('mind_map_refresh')));
    await tester.pumpAndSettle();
    expect(find.text('Saved memory'), findsOneWidget);
    expect(calls, 2);
    await tester.pump(const Duration(seconds: 9));
  });

  testWidgets('a failed refresh on app resume keeps the map without a toast', (tester) async {
    var calls = 0;
    await tester.pumpWidget(_app(MemoryGraphPage(
        trackOpenEvent: false,
        loadGraph: () async {
          if (++calls > 1) throw Exception('offline');
          return {
            'nodes': [],
            'edges': [],
            'catalog_nodes': [
              {'id': 'memory:1', 'label': 'Saved memory'}
            ]
          };
        })));
    await tester.pumpAndSettle();
    final l10n = AppLocalizations.of(tester.element(find.byType(MemoryGraphPage)));

    // The page stays alive on Home's other tabs, so a resume refresh must not speak over them.
    tester
        .state<MemoryGraphPageState>(find.byType(MemoryGraphPage))
        .didChangeAppLifecycleState(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(calls, 2);
    expect(find.text('Saved memory'), findsOneWidget);
    expect(find.text(l10n.couldNotLoadKnowledgeGraph), findsNothing);

    // A refresh the person asked for still says it failed.
    await tester.tap(find.byKey(const ValueKey('mind_map_refresh')));
    await tester.pumpAndSettle();
    expect(calls, 3);
    expect(find.text(l10n.couldNotLoadKnowledgeGraph), findsOneWidget);
    await tester.pump(const Duration(seconds: 9));
  });

  testWidgets('a late empty response cannot overwrite a newer graph or its labels', (tester) async {
    final old = Completer<Map<String, dynamic>>();
    var calls = 0;
    await tester.pumpWidget(_app(MemoryGraphPage(
        trackOpenEvent: false,
        loadGraph: () async {
          if (++calls == 1) return old.future;
          return {
            'nodes': [
              {'id': 'hiking', 'label': calls == 2 ? 'Hiking' : 'Corrected hiking'}
            ],
            'edges': []
          };
        })));
    final state = tester.state<MemoryGraphPageState>(find.byType(MemoryGraphPage));
    state.didChangeAppLifecycleState(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    old.complete({'nodes': [], 'edges': []});
    await tester.pumpAndSettle();
    expect(state.simulation.nodes.any((n) => n.label == 'Hiking'), true);
    await tester.tap(find.byKey(const ValueKey('mind_map_refresh')));
    await tester.pumpAndSettle();
    expect(state.simulation.nodes.any((n) => n.label == 'Corrected hiking'), true);
  });

  testWidgets('changed authorization clears previously readable memories', (tester) async {
    var calls = 0;
    await tester.pumpWidget(_app(MemoryGraphPage(
        trackOpenEvent: false,
        loadGraph: () async {
          if (++calls > 1) throw const KnowledgeGraphSessionChanged();
          return {
            'nodes': [],
            'edges': [],
            'catalog_nodes': [
              {'id': 'memory:1', 'label': 'Previous account memory'}
            ]
          };
        })));
    await tester.pumpAndSettle();
    expect(find.text('Previous account memory'), findsOneWidget);
    await tester.tap(find.byKey(const ValueKey('mind_map_refresh')));
    await tester.pumpAndSettle();
    expect(find.text('Previous account memory'), findsNothing);
    expect(find.byKey(const ValueKey('mind_map_memory_catalog')), findsNothing);
  });

  testWidgets('large canonical pages keep the force simulation bounded', (tester) async {
    await tester.pumpWidget(_app(MemoryGraphPage(
        trackOpenEvent: false,
        loadGraph: () async => {
              'nodes': [
                for (var i = 0; i < 500; i++) {'id': 'entity:$i', 'label': 'Entity $i'}
              ],
              'edges': [],
            })));
    await tester.pump();
    final state = tester.state<MemoryGraphPageState>(find.byType(MemoryGraphPage));
    expect(state.simulation.nodes.length, lessThanOrEqualTo(201));
    await tester.pumpWidget(const SizedBox());
  });

  testWidgets('expired cursor drops the old revision even when its restart fails', (tester) async {
    var calls = 0;
    await tester.pumpWidget(_app(MemoryGraphPage(
      trackOpenEvent: false,
      loadGraph: () async {
        if (++calls > 1) throw Exception('offline');
        return {
          'nodes': [],
          'edges': [],
          'catalog_nodes': [
            {'id': 'memory:1', 'label': 'Old revision'}
          ],
          'has_more': true,
          'next_cursor': 'stale'
        };
      },
      loadMoreGraph: (_) async => throw const KnowledgeGraphCursorExpired(),
    )));
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const ValueKey('mind_map_load_more')));
    await tester.pumpAndSettle();
    expect(calls, 2);
    expect(find.text('Old revision'), findsNothing);
    expect(find.byKey(const ValueKey('mind_map_memory_catalog')), findsNothing);
  });

  testWidgets('a changed graph clears stale selection highlights after refresh', (tester) async {
    var calls = 0;
    await tester.pumpWidget(_app(MemoryGraphPage(
        trackOpenEvent: false,
        loadGraph: () async => {
              'nodes': [
                {'id': ++calls == 1 ? 'first' : 'second', 'label': 'A memory entity'}
              ],
              'edges': [],
            })));
    await tester.pumpAndSettle();
    final canvas = find.byWidgetPredicate((widget) => widget is CustomPaint && widget.painter is GraphPainter3D);
    await tester.tapAt(tester.getCenter(canvas));
    await tester.pumpAndSettle();
    expect((tester.widget<CustomPaint>(canvas).painter as GraphPainter3D).highlightedNodeIds, isNotEmpty);
    await tester.tap(find.byKey(const ValueKey('mind_map_refresh')));
    await tester.pumpAndSettle();
    expect((tester.widget<CustomPaint>(canvas).painter as GraphPainter3D).highlightedNodeIds, isEmpty);
  });
}
