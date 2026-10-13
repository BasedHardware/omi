import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/pages/apps/widgets/category_section.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

// Regression test for #19238: CategorySection rows overflow at larger text sizes
// (e.g. 1.15x, 1.3x, 1.5x) when targetItemHeight and titleSectionHeight are fixed.
// Heights must scale dynamically with text size to prevent overflow.

App _testApp({required String id, required String name, required String category, double? ratingAvg}) {
  return App(
    id: id,
    name: name,
    author: 'Community',
    description: 'A test application description',
    image: '',
    capabilities: const {'chat'},
    status: 'approved',
    category: category,
    approved: true,
    ratingAvg: ratingAvg,
    ratingCount: ratingAvg != null ? 42 : 0,
    installs: 100,
    enabled: false,
    deleted: false,
    isPaid: false,
    isUserPaid: false,
  );
}

Widget _buildHarness({
  required Widget child,
  required double textScale,
  required double width,
}) {
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<AppProvider>.value(value: AppProvider()),
      ChangeNotifierProvider<AddAppProvider>.value(value: AddAppProvider()),
    ],
    child: MaterialApp(
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: MediaQuery(
        data: MediaQueryData(
          size: Size(width, 844),
          textScaler: TextScaler.linear(textScale),
        ),
        child: Scaffold(
          body: SingleChildScrollView(
            child: child,
          ),
        ),
      ),
    ),
  );
}

void main() {
  setUpAll(() {
    PlatformManager.initializeForLocalHarness();
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  final testApps = [
    _testApp(id: 'app-1', name: 'Productivity Booster Pro', category: 'productivity', ratingAvg: 4.8),
    _testApp(id: 'app-2', name: 'Focus Timer & Tasks', category: 'productivity', ratingAvg: 4.5),
    _testApp(id: 'app-3', name: 'Daily Habit Tracker Plus', category: 'productivity', ratingAvg: 4.9),
  ];

  testWidgets('CategorySection lays out without overflow across standard and larger text sizes', (tester) async {
    // Issue #19238 reported overflows at 1.15x, 1.3x, and 1.5x on a 390 pt wide viewport.
    const textScales = [1.0, 1.15, 1.3, 1.5];
    const testWidth = 390.0;

    for (final scale in textScales) {
      await tester.pumpWidget(
        _buildHarness(
          textScale: scale,
          width: testWidth,
          child: CategorySection(
            categoryName: 'Productivity',
            apps: testApps,
            onViewAll: () {},
          ),
        ),
      );
      await tester.pump();

      final cardFinder = find.byType(SectionAppItemCard).first;
      final renderedStack =
          tester.getSize(find.descendant(of: cardFinder, matching: find.text('Productivity Booster Pro'))).height +
              tester.getSize(find.descendant(of: cardFinder, matching: find.text('Productivity'))).height +
              tester.getSize(find.descendant(of: cardFinder, matching: find.textContaining('4.8'))).height +
              4;
      final renderedCardHeight = tester.getSize(cardFinder).height;
      final expectedTargetHeight = const [85.0, 88.0, 97.0, 109.0][textScales.indexOf(scale)];

      expect(
        renderedCardHeight,
        expectedTargetHeight,
        reason: 'The measured card target should follow rendered text height at $scale scale.',
      );
      expect(
        renderedCardHeight,
        greaterThanOrEqualTo(renderedStack + 16),
        reason: 'Card text and its vertical padding must fit at $scale scale.',
      );
      expect(
        tester.takeException(),
        isNull,
        reason: 'CategorySection should not overflow at scale  on width ',
      );
      // The heading and each app card display this category label.
      expect(find.text('Productivity'), findsNWidgets(testApps.length + 1));
      expect(find.text('Productivity Booster Pro'), findsOneWidget);
    }
  });

  testWidgets('CategorySection preserves card layout and displays all category apps without errors', (tester) async {
    await tester.pumpWidget(
      _buildHarness(
        textScale: 1.3,
        width: 390.0,
        child: CategorySection(
          categoryName: 'Productivity',
          apps: testApps,
          onViewAll: () {},
        ),
      ),
    );
    await tester.pump();

    expect(tester.takeException(), isNull);
    expect(find.text('Productivity Booster Pro'), findsOneWidget);
    expect(find.text('Focus Timer & Tasks'), findsOneWidget);
    expect(find.text('Daily Habit Tracker Plus'), findsOneWidget);
  });
}
