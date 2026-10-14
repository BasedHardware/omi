import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/settings_drawer.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/user_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/platform/platform_manager.dart';

// Regression test for #19241: Settings opening search makes every row jump 12 pt,
// and the field sits 4 pt off the cards. Header height must remain constant (48 pt)
// and search field must align with the settings cards (padding left OmiSpacing.lg = 20 pt).

Widget _buildHarness() {
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<AppProvider>.value(value: AppProvider()),
      ChangeNotifierProvider<HomeProvider>.value(value: HomeProvider()),
      ChangeNotifierProvider<UserProvider>.value(value: UserProvider()),
      ChangeNotifierProvider<UsageProvider>.value(value: UsageProvider()),
    ],
    child: const MaterialApp(
      localizationsDelegates: [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: Scaffold(
        body: SettingsDrawer(),
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

  testWidgets('opening and closing search maintains header height and card vertical position', (tester) async {
    await tester.pumpWidget(_buildHarness());
    await tester.pumpAndSettle();

    // 1. Initial normal header
    final normalHeader = find.byKey(const ValueKey('normal-header'));
    expect(normalHeader, findsOneWidget);
    final initialHeaderHeight = tester.getSize(normalHeader).height;
    expect(initialHeaderHeight, 48.0);

    // Record top position of the settings list content
    final listFinder = find.byType(SingleChildScrollView);
    expect(listFinder, findsOneWidget);
    final initialListTop = tester.getTopLeft(listFinder).dy;

    // 2. Tap search icon to open search header
    final searchButton = find.widgetWithIcon(OmiIconButton, Icons.search);
    expect(searchButton, findsOneWidget);
    await tester.tap(searchButton);
    await tester.pumpAndSettle();

    // 3. Search header active
    final searchHeader = find.byKey(const ValueKey('search-header'));
    expect(searchHeader, findsOneWidget);
    final searchHeaderHeight = tester.getSize(searchHeader).height;
    expect(searchHeaderHeight, 48.0);

    // List top should remain exactly the same (no 12 pt jump)
    final afterOpenListTop = tester.getTopLeft(listFinder).dy;
    expect(afterOpenListTop, initialListTop);

    // Search field should align with the cards (left at 20 pt = OmiSpacing.lg)
    final searchFieldFinder = find.byType(OmiSearchField);
    expect(searchFieldFinder, findsOneWidget);
    expect(tester.getTopLeft(searchFieldFinder).dx, OmiSpacing.lg);

    // 4. Tap Cancel to return to normal header
    final cancelButton = find.widgetWithText(OmiButton, 'Cancel');
    expect(cancelButton, findsOneWidget);
    await tester.tap(cancelButton);
    await tester.pumpAndSettle();

    // Normal header restored and list top position unchanged
    expect(find.byKey(const ValueKey('normal-header')), findsOneWidget);
    final afterCloseListTop = tester.getTopLeft(listFinder).dy;
    expect(afterCloseListTop, initialListTop);
  });
}
