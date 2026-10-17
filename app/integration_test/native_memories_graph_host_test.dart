import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/memories.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/memories/page.dart';
import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/pages/onboarding/knowledge_graph_step.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_step_layout.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/services/auth_service.dart';

import 'journeys/support/hermetic_boot.dart';
import 'support/native_host_harness.dart';

Future<Map<String, dynamic>> _graph() async => {
      'nodes': [
        {'id': 'ada', 'label': 'Ada', 'node_type': 'person'},
        {'id': 'paris', 'label': 'Paris', 'node_type': 'place'},
        {'id': 'omi', 'label': 'Omi', 'node_type': 'organization'},
      ],
      'edges': [
        {'source_id': 'ada', 'target_id': 'paris', 'label': 'visited'},
        {'source_id': 'ada', 'target_id': 'omi', 'label': 'works at'},
      ],
    };

final _memory = Memory(
  id: 'host-memory',
  uid: 'host-owner',
  content: 'Prefers morning walks',
  category: MemoryCategory.system,
  createdAt: DateTime.utc(2026, 9, 1),
  updatedAt: DateTime.utc(2026, 9, 1),
  visibility: MemoryVisibility.private,
);

/// The graph row of the topmost native surface.
Map _canvas(WidgetTester tester) => nativeProjectedRow(tester, 'memory_graph_canvas').projection;

/// Simulator-only: flutter drive --driver integration_test/native_ui_host_driver.dart
/// --target integration_test/native_memories_graph_host_test.dart --flavor dev
/// --dart-define=OMI_APP_PROFILE=local_dev --dart-define=OMI_IOS_SWIFTUI=true -d <simulator-id>
void main() {
  runNativeHostSuite((checkNativeHost) {
    testWidgets('Memories shows the mind map card, which opens the native graph; selection, share and sign-out',
        (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      await tester.pumpWidget(nativeHostApp(const MemoriesPage(loadGraph: _graph), providers: [
        ChangeNotifierProvider(
            create: (_) => MemoriesProvider(
                fetchMemoriesRequest: ({limit = 100, offset = 0, thisDeviceOnly = false}) async =>
                    GetMemoriesResult([_memory], true))),
      ]));
      await tester.pump(const Duration(seconds: 1));

      await checkNativeHost(tester, 'native-memories-knowledge-graph-memories-dark');
      final card = nativeProjectedRow(tester, 'memory_graph_preview');
      expect(card.graph?.layout, 'card');
      expect(card.graph?.placeholder, isFalse);
      expect(nativeProjectedRow(tester, 'memory_host-memory').title, 'Prefers morning walks');

      // The card's tap pushes the full graph; the row stays pending natively while it is open.
      card.action!(null);
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
      expect(find.byType(MemoryGraphPage), findsOneWidget);
      await checkNativeHost(tester, 'native-memories-knowledge-graph-graph-dark');
      expect(_canvas(tester)['value'], '');

      await nativeProjectedRow(tester, 'memory_graph_canvas').action!('ada');
      await tester.pump(const Duration(seconds: 1));
      expect(_canvas(tester)['value'], 'ada');
      expect((_canvas(tester)['graph'] as Map)['highlighted'], ['ada', 'omi', 'paris']);
      await checkNativeHost(tester, 'native-memories-knowledge-graph-graph-selected-dark');

      final surface = tester.widget<IosNativeSurface>(find.byType(IosNativeSurface).last);
      expect(nativeProjectedRow(tester, 'memory_graph_share').enabled, isTrue);
      final image = await surface.controller!.captureImage(target: 'memory_graph_canvas');
      expect(image, isNotNull, reason: 'Share receives the rendered graph row');

      // Signing out invalidates the native graph and its capture.
      AuthService.instance.handleAuthUserChanged(null);
      await tester.pump(const Duration(seconds: 1));
      expect(await surface.controller!.captureImage(target: 'memory_graph_canvas'), isNull);
      expect(find.byType(UiKitView), findsNothing);
    });

    testWidgets('the onboarding knowledge graph step renders natively with progress and back', (tester) async {
      await JourneyHermeticBoot.start(extraPrefs: {'appearanceMode': 'dark'});
      addTearDown(JourneyHermeticBoot.stop);
      var continued = 0, back = 0, rebuilds = 0;
      late StateSetter rebuildParent;
      await tester.pumpWidget(nativeHostApp(Scaffold(
        body: StatefulBuilder(builder: (context, setState) {
          rebuildParent = setState;
          rebuilds++;
          return OnboardingStepLayout(
            nativeNavigation: true,
            nativeProgress: 'Step 7 of 8',
            reserveHeader: false,
            onBack: () => back++,
            child: OnboardingKnowledgeGraphStep(onContinue: () => continued++, loadGraph: _graph),
          );
        }),
      )));
      await tester.pump(const Duration(seconds: 1));

      await checkNativeHost(tester, 'native-memories-knowledge-graph-onboarding-dark');
      expect(nativeProjectedRow(tester, 'onboarding_progress_label').title, 'Step 7 of 8');
      expect(nativeProjectedRow(tester, 'onboarding_kg_graph').graph?.placeholder, isFalse);
      final view = nativeViewId(tester, find.byType(UiKitView));

      rebuildParent(() {});
      await tester.pump(const Duration(seconds: 1));
      expect(rebuilds, greaterThanOrEqualTo(2));
      expect(nativeViewId(tester, find.byType(UiKitView)), view, reason: 'a parent rebuild keeps the native view');
      await checkNativeHost(tester, 'native-memories-knowledge-graph-onboarding-rebuilt-dark');

      await nativeProjectedRow(tester, 'onboarding_back').action!(null);
      await nativeProjectedRow(tester, 'onboarding_knowledge_graph_continue').action!(null);
      expect([back, continued], [1, 1]);
    });
  });
}
