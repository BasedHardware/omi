import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/apps/add_app.dart';
import 'package:omi/pages/apps/providers/add_app_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/ui/ui.dart';

// Regression tests for the manual route in #24723: Submit App stayed grey with no reason. A tap
// on the disabled button now runs the submit validation, so the unmet requirement is named. The
// per-capability checks in that validation also compared display titles ("Chat") to ids ("chat")
// and could never fire; they compare ids now.

/// A valid 1x1 PNG, so the logo slot holds a chosen file like a real form.
const _onePixelPng = 'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=';

/// The capabilities exactly as GET /v1/app-capabilities names them: display titles over
/// lowercase ids.
final List<AppCapability> _capabilities = [
  AppCapability(title: 'Chat', id: 'chat'),
  AppCapability(title: 'External Integration', id: 'external_integration'),
];

/// A provider whose catalog data is already loaded, so the page's init makes no requests, and
/// whose name, description and category are filled in. Capabilities and the logo are left to
/// each test.
AddAppProvider _filledProvider() {
  final provider = AddAppProvider()
    ..categories = [Category(title: 'Productivity', id: 'productivity-and-organization')]
    ..capabilities = _capabilities
    ..paymentPlans = [PaymentPlan(title: 'Monthly', id: 'monthly_recurring')]
    ..appCategory = 'productivity-and-organization';
  provider.appNameController.text = 'Standup Notes';
  provider.appDescriptionController.text = 'Turns each standup into a short note.';
  return provider;
}

Widget _harness(AddAppProvider provider) {
  return MultiProvider(
    providers: [
      ChangeNotifierProvider<AppProvider>(create: (_) => AppProvider()),
      ChangeNotifierProvider<AddAppProvider>.value(value: provider),
    ],
    child: MaterialApp(
      // The validation copy and its snackbar go through the global navigator key.
      navigatorKey: globalNavigatorKey,
      localizationsDelegates: const [
        AppLocalizations.delegate,
        GlobalMaterialLocalizations.delegate,
        GlobalWidgetsLocalizations.delegate,
        GlobalCupertinoLocalizations.delegate,
      ],
      supportedLocales: AppLocalizations.supportedLocales,
      home: const AddAppPage(),
    ),
  );
}

void main() {
  final en = lookupAppLocalizations(const Locale('en'));
  late Directory tempDir;

  setUpAll(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  setUp(() {
    tempDir = Directory.systemTemp.createTempSync('add-app-submit-');
  });

  tearDown(() {
    tempDir.deleteSync(recursive: true);
  });

  Finder submitButton() => find.widgetWithText(OmiButton, en.submitApp);

  Future<void> pumpForm(WidgetTester tester, AddAppProvider provider) async {
    await tester.pumpWidget(_harness(provider));
    await tester.pumpAndSettle();
    expect(submitButton(), findsOneWidget);
    expect(tester.widget<OmiButton>(submitButton()).onPressed, isNull, reason: 'the form is not complete');
  }

  /// Snackbars hold a timer; drain it so the test ends with no pending work.
  Future<void> drainSnackbar(WidgetTester tester) async {
    await tester.pump(const Duration(seconds: 10));
    await tester.pumpAndSettle();
  }

  testWidgets('a tap on the disabled Submit App names the missing requirement', (tester) async {
    final provider = _filledProvider();
    await pumpForm(tester, provider);

    await tester.tap(submitButton());
    await tester.pump();

    expect(find.text(en.addAppSelectCapability), findsOneWidget);
    expect(find.text(en.submitAppQuestion), findsNothing, reason: 'nothing is submitted');
    await drainSnackbar(tester);
  });

  testWidgets('a capability-specific requirement is named, not a generic or unrelated one', (tester) async {
    // Everything but the trigger event is in place: an External Integration app with a logo, a
    // source URL and no trigger. The readiness check already knows the trigger is missing.
    final provider = _filledProvider()
      ..imageFile = (File('${tempDir.path}/logo.png')..writeAsBytesSync(base64Decode(_onePixelPng)))
      ..selectedCapabilities = [_capabilities.last];
    provider.sourceCodeUrlController.text = 'https://github.com/example/standup-notes';
    await pumpForm(tester, provider);

    await tester.tap(submitButton());
    await tester.pump();

    expect(find.text(en.addAppSelectTriggerEvent), findsOneWidget);
    expect(find.text(en.addAppFillRequiredFields), findsNothing);
    expect(find.text(en.githubRepositoryUrlRequired), findsNothing);
    await drainSnackbar(tester);
  });
}
