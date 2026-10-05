import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
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

    test('only backend labels and the given name identify the user node', () {
      expect(memoryGraphKnownUserLabels(''), {'me', 'the user'});
      expect(memoryGraphKnownUserLabels(' Ana '), {'me', 'the user', 'ana'});
      expect(memoryGraphKnownUserLabels('').contains('tú'), isFalse);
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
}
