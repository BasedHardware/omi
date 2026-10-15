import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/language_selection_dialog.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/ui/components/omi_nav_buttons.dart';

/// The primary-language sheet is never a dead end: with no language saved it still has a close
/// button and answers a scrim tap, and Home offers it once per session, not on every rebuild.
void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  Future<HomeProvider> pumpHost(WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
    final homeProvider = HomeProvider();
    addTearDown(homeProvider.dispose);
    tester.view.physicalSize = const Size(1179, 2556);
    tester.view.devicePixelRatio = 3;
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(
      ChangeNotifierProvider<HomeProvider>.value(
        value: homeProvider,
        child: MaterialApp(
          localizationsDelegates: const [
            AppLocalizations.delegate,
            GlobalMaterialLocalizations.delegate,
            GlobalWidgetsLocalizations.delegate,
            GlobalCupertinoLocalizations.delegate,
          ],
          supportedLocales: AppLocalizations.supportedLocales,
          home: Scaffold(
            body: Builder(
              builder: (context) => Center(
                child: TextButton(
                  onPressed: () => context.read<HomeProvider>().showLanguageDialogIfNeeded(context),
                  child: const Text('offer'),
                ),
              ),
            ),
          ),
        ),
      ),
    );
    return homeProvider;
  }

  testWidgets('with no language saved the sheet still has a close button that dismisses it', (tester) async {
    final homeProvider = await pumpHost(tester);
    expect(homeProvider.hasSetPrimaryLanguage, isFalse);

    await tester.tap(find.text('offer'));
    await tester.pumpAndSettle();

    expect(find.text('Tell us your primary language'), findsOneWidget);
    expect(find.byType(OmiCloseButton), findsOneWidget);

    await tester.tap(find.byType(OmiCloseButton));
    await tester.pumpAndSettle();

    expect(find.text('Tell us your primary language'), findsNothing);
    expect(homeProvider.hasSetPrimaryLanguage, isFalse, reason: 'closing saves nothing; the default stays');
  });

  testWidgets('a scrim tap closes it too', (tester) async {
    await pumpHost(tester);
    await tester.tap(find.text('offer'));
    await tester.pumpAndSettle();
    expect(find.text('Tell us your primary language'), findsOneWidget);

    await tester.tapAt(const Offset(20, 20));
    await tester.pumpAndSettle();

    expect(find.text('Tell us your primary language'), findsNothing);
  });

  testWidgets('Home offers the sheet once per session, again after the account changes', (tester) async {
    final homeProvider = await pumpHost(tester);

    await tester.tap(find.text('offer'));
    await tester.pumpAndSettle();
    await tester.tap(find.byType(OmiCloseButton));
    await tester.pumpAndSettle();

    // The next Home rebuild asks again; the user already said no.
    await tester.tap(find.text('offer'));
    await tester.pumpAndSettle();
    expect(find.text('Tell us your primary language'), findsNothing);

    homeProvider.clearUserData();
    await tester.tap(find.text('offer'));
    await tester.pumpAndSettle();
    expect(find.text('Tell us your primary language'), findsOneWidget);
  });

  testWidgets('a direct request reopens it even when a language is set', (tester) async {
    final homeProvider = await pumpHost(tester);
    homeProvider.userPrimaryLanguage = 'es';
    homeProvider.hasSetPrimaryLanguage = true;

    await tester.tap(find.text('offer'));
    await tester.pumpAndSettle();
    expect(find.text('Tell us your primary language'), findsNothing);

    final context = tester.element(find.text('offer'));
    LanguageSelectionDialog.show(context, forceShow: true);
    await tester.pumpAndSettle();
    expect(find.text('Tell us your primary language'), findsOneWidget);
    expect(find.byType(OmiCloseButton), findsOneWidget);
  });
}
