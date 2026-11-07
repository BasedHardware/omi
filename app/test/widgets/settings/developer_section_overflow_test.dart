import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/developer_mcp_section.dart';
import 'package:omi/pages/settings/widgets/developer_api_keys_section.dart';
import 'package:omi/providers/dev_api_key_provider.dart';
import 'package:omi/providers/mcp_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';

void main() {
  for (final locale in [const Locale('en'), const Locale('de'), const Locale('fr')]) {
    testWidgets('Developer sections do not overflow on narrow screens at 1.3x text size in $locale', (tester) async {
      tester.view.physicalSize = const Size(320, 600);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final devApiKeyProvider = DevApiKeyProvider();
      final mcpProvider = McpProvider();
      final usageProvider = UsageProvider();
      addTearDown(devApiKeyProvider.dispose);
      addTearDown(mcpProvider.dispose);
      addTearDown(usageProvider.dispose);

      await tester.pumpWidget(
        MultiProvider(
          providers: [
            ChangeNotifierProvider<McpProvider>.value(value: mcpProvider),
            ChangeNotifierProvider<UsageProvider>.value(value: usageProvider),
          ],
          child: MaterialApp(
            locale: locale,
            localizationsDelegates: const [
              AppLocalizations.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            supportedLocales: AppLocalizations.supportedLocales,
            home: MediaQuery(
              data: const MediaQueryData(
                size: Size(320, 600),
                textScaler: TextScaler.linear(1.3),
              ),
              child: Scaffold(
                body: SingleChildScrollView(
                  padding: const EdgeInsets.all(16),
                  child: Column(
                    children: [
                      DeveloperApiKeysSection(provider: devApiKeyProvider),
                      const SizedBox(height: 24),
                      const DeveloperMcpSection(),
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      );

      await tester.pump();
      expect(tester.takeException(), isNull);
    });
  }

  testWidgets('OmiSectionHeader wraps trailing widget under title when space is constrained', (tester) async {
    tester.view.physicalSize = const Size(200, 300);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: Padding(
            padding: EdgeInsets.all(8),
            child: OmiSectionHeader(
              'A very long section title that needs space',
              trailing: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text('Action 1'),
                  SizedBox(width: 8),
                  Text('Action 2'),
                ],
              ),
            ),
          ),
        ),
      ),
    );

    await tester.pump();
    expect(tester.takeException(), isNull);
    final titleFinder = find.text('A very long section title that needs space');
    final action1Finder = find.text('Action 1');
    final action2Finder = find.text('Action 2');
    expect(titleFinder, findsOneWidget);
    expect(action1Finder, findsOneWidget);
    expect(action2Finder, findsOneWidget);

    final titleBottom = tester.getBottomLeft(titleFinder).dy;
    final action1Top = tester.getTopLeft(action1Finder).dy;
    final action2Right = tester.getTopRight(action2Finder).dx;
    expect(action1Top, greaterThanOrEqualTo(titleBottom));
    expect(action2Right, lessThanOrEqualTo(200.0));
  });

  testWidgets('OmiSectionHeader aligns trailing widget to the right edge on wide screens', (tester) async {
    tester.view.physicalSize = const Size(500, 300);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      const MaterialApp(
        home: Scaffold(
          body: Padding(
            padding: EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                OmiSectionHeader(
                  'Short Title',
                  trailing: Text('Trailing Action'),
                ),
              ],
            ),
          ),
        ),
      ),
    );

    await tester.pump();
    expect(tester.takeException(), isNull);

    final headerTopRight = tester.getTopRight(find.byType(OmiSectionHeader));
    final trailingTopRight = tester.getTopRight(find.text('Trailing Action'));
    // The trailing text is flush right inside the header padding (right padding is OmiSpacing.xxs = 4.0)
    expect((headerTopRight.dx - trailingTopRight.dx).abs(), lessThanOrEqualTo(5.0));
  });
}
