import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/utils/platform/platform_manager.dart';

Future<Map<String, dynamic>> _emptyGraph() async => {'nodes': [], 'edges': []};

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
}
