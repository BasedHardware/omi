import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/env/env.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/ai_app_generator_page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/platform/platform_manager.dart';

// Regression test for #19239: AI app generator suggestion cards overflow at
// larger text sizes (e.g. 1.15x, 1.3x, 1.5x) when the strip height is fixed at 160 pt.
// The suggestion strip height must scale dynamically with MediaQuery.textScalerOf(context).

final class _TestEnvFields implements EnvFields {
  const _TestEnvFields();

  @override
  String? get apiBaseUrl => 'http://127.0.0.1:9/';

  @override
  String? get googleClientId => null;

  @override
  String? get googleClientSecret => null;

  @override
  String? get intercomAppId => null;

  @override
  String? get intercomIOSApiKey => null;

  @override
  String? get intercomAndroidApiKey => null;

  @override
  String? get posthogApiKey => null;

  @override
  bool? get useAuthCustomToken => false;

  @override
  bool? get useWebAuth => false;
}

Widget _buildHarness({
  required Widget child,
  required double textScale,
  required double width,
}) {
  return ChangeNotifierProvider<AppProvider>.value(
    value: AppProvider(),
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
        child: child,
      ),
    ),
  );
}

void main() {
  setUpAll(() {
    Env.init(const _TestEnvFields());
    PlatformManager.initializeForLocalHarness();
  });

  setUp(() async {
    SharedPreferences.setMockInitialValues({});
    await SharedPreferencesUtil.init();
  });

  testWidgets('AI app generator suggestion cards scale without overflow at larger text sizes', (tester) async {
    // Issue #19239 reported bottom overflows by 6 pt at 1.15x, 15 pt at 1.3x, and 30 pt at 1.5x.
    const textScales = [1.0, 1.15, 1.3, 1.5];
    const testWidth = 390.0;

    for (final scale in textScales) {
      await tester.pumpWidget(
        _buildHarness(
          textScale: scale,
          width: testWidth,
          child: const AiAppGeneratorPage(),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 500));

      expect(
        tester.takeException(),
        isNull,
        reason: 'AI app generator suggestion strip should not overflow at scale $scale on width $testWidth',
      );
      // The localized label includes an ellipsis. While the prompt request is
      // pending, the horizontal strip renders its loading cards; no network
      // response is required to verify their layout.
      expect(find.text('Try something like…'), findsOneWidget);
      expect(find.text('A playful gratitude spinner for daily positivity'), findsOneWidget);
      expect(
        find.byWidgetPredicate((widget) => widget is ListView && widget.scrollDirection == Axis.horizontal),
        findsOneWidget,
      );
    }
  });
}
