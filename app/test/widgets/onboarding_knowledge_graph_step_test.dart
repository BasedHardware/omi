import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/pages/onboarding/knowledge_graph_step.dart';

void main() {
  testWidgets('knowledge graph step is a single-line heading with no map subtitle', (tester) async {
    await tester.pumpWidget(
      MaterialApp(
        localizationsDelegates: const [
          AppLocalizations.delegate,
          GlobalMaterialLocalizations.delegate,
          GlobalWidgetsLocalizations.delegate,
          GlobalCupertinoLocalizations.delegate,
        ],
        supportedLocales: AppLocalizations.supportedLocales,
        home: OnboardingKnowledgeGraphStep(onContinue: () {}),
      ),
    );
    await tester.pump();

    final title = tester.widget<Text>(find.text('Here is what I know about you.'));
    expect(title.maxLines, 1);
    expect(title.softWrap, isFalse);
    expect(find.textContaining('This map updates'), findsNothing);
    expect(find.textContaining('map updates as Omi'), findsNothing);

    final padding = tester.widget<Padding>(find.byKey(const Key('onboardingKnowledgeGraphPadding')));
    expect(padding.padding, const EdgeInsets.fromLTRB(24, kOnboardingKnowledgeGraphTitleTopPadding, 24, 24));
    expect(kOnboardingKnowledgeGraphTitleTopPadding, greaterThan(80));

    final graph = tester.widget<MemoryGraphPage>(find.byType(MemoryGraphPage));
    expect(graph.embedded, isTrue);
    expect(graph.flat2d, isTrue);
    expect(graph.pollWhileEmpty, isTrue);
    expect(graph.loadFallbackGraph, isNotNull);
  });
}
