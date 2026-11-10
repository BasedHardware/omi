import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/pages/onboarding/knowledge_graph_step.dart';
import 'package:omi/utils/platform/platform_manager.dart';

Future<Map<String, dynamic>> _sampleFiveNodeGraph() async => {
      'nodes': [
        {'id': '1', 'label': 'Sam', 'node_type': 'user'},
        {'id': '2', 'label': 'Coffee', 'node_type': 'thing'},
        {'id': '3', 'label': 'Work', 'node_type': 'thing'},
        {'id': '4', 'label': 'Alice', 'node_type': 'person'},
        {'id': '5', 'label': 'Gym', 'node_type': 'place'},
      ],
      'edges': [
        {'source_id': '1', 'target_id': '2', 'label': 'drinks'},
        {'source_id': '1', 'target_id': '3', 'label': 'works_at'},
        {'source_id': '1', 'target_id': '4', 'label': 'knows'},
        {'source_id': '1', 'target_id': '5', 'label': 'goes_to'},
      ]
    };

Widget _app(Widget home) {
  return MaterialApp(
    localizationsDelegates: AppLocalizations.localizationsDelegates,
    supportedLocales: AppLocalizations.supportedLocales,
    home: MediaQuery(
      data: const MediaQueryData(size: Size(375, 812), padding: EdgeInsets.only(top: 47, bottom: 34)),
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

  group('MemoryGraphPage fitToBounds', () {
    testWidgets('scales zoom down to fit node bounds within viewport when fitToBounds is true', (tester) async {
      await tester.binding.setSurfaceSize(const Size(360, 500));
      addTearDown(() => tester.binding.setSurfaceSize(null));

      await tester.pumpWidget(
        _app(
          const Scaffold(
            body: SizedBox(
              width: 360,
              height: 500,
              child: MemoryGraphPage(
                embedded: true,
                trackOpenEvent: false,
                showAppBar: false,
                showShareButton: false,
                initialZoom: 0.72,
                fitToBounds: true,
                loadGraph: _sampleFiveNodeGraph,
              ),
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      final state = tester.state<MemoryGraphPageState>(find.byType(MemoryGraphPage));
      expect(state, isNotNull);
      expect(state.hasFittedBounds, isTrue);
      expect(state.zoom, lessThan(0.72));
    });

    testWidgets('OnboardingKnowledgeGraphStep configures MemoryGraphPage with fitToBounds', (tester) async {
      await tester.pumpWidget(
        _app(
          Scaffold(
            body: OnboardingKnowledgeGraphStep(
              onContinue: () {},
            ),
          ),
        ),
      );

      final graphPage = tester.widget<MemoryGraphPage>(find.byType(MemoryGraphPage));
      expect(graphPage.fitToBounds, isTrue);
      expect(graphPage.embedded, isTrue);
      expect(graphPage.initialZoom, 0.72);
    });
  });
}
