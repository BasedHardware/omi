import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/auth.dart';
import 'package:omi/pages/onboarding/complete_screen.dart';
import 'package:omi/pages/onboarding/knowledge_graph_step.dart';
import 'package:omi/providers/auth_provider.dart';

bool _hasRoundedDrawerCard(Widget widget) {
  if (widget is! Container) return false;
  final decoration = widget.decoration;
  if (decoration is! BoxDecoration) return false;
  final radius = decoration.borderRadius;
  if (radius is! BorderRadius) return false;
  return radius.topLeft == const Radius.circular(40) && radius.topRight == const Radius.circular(40);
}

void main() {
  testWidgets('onboarding pages do not use a mid-screen rounded drawer card', (tester) async {
    final authProvider = AuthenticationProvider(initializeListeners: false);
    addTearDown(authProvider.dispose);

    Future<void> pump(Widget child) async {
      await tester.pumpWidget(
        ChangeNotifierProvider<AuthenticationProvider>.value(
          value: authProvider,
          child: MaterialApp(
            localizationsDelegates: const [
              AppLocalizations.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            supportedLocales: AppLocalizations.supportedLocales,
            home: Scaffold(backgroundColor: Colors.black, body: child),
          ),
        ),
      );
      await tester.pump();
    }

    await pump(AuthComponent(onSignIn: () {}));
    expect(tester.widgetList(find.byType(Container)).where(_hasRoundedDrawerCard), isEmpty);

    await pump(OnboardingCompleteScreen(onComplete: () {}));
    await tester.pump(const Duration(milliseconds: 300));
    expect(tester.widgetList(find.byType(Container)).where(_hasRoundedDrawerCard), isEmpty);

    await pump(OnboardingKnowledgeGraphStep(onContinue: () {}));
    await tester.pump();
    expect(tester.widgetList(find.byType(Container)).where(_hasRoundedDrawerCard), isEmpty);
  });
}
