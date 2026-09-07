import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/auth.dart';
import 'package:omi/pages/onboarding/complete_screen.dart';
import 'package:omi/providers/auth_provider.dart';

const Radius _drawerRadius = Radius.circular(40);

bool _hasDrawerTopCorners(BorderRadiusGeometry? radius) {
  if (radius is BorderRadius) {
    return radius.topLeft == _drawerRadius && radius.topRight == _drawerRadius;
  }
  if (radius is BorderRadiusDirectional) {
    return radius.topStart == _drawerRadius && radius.topEnd == _drawerRadius;
  }
  return false;
}

bool _decorationIsDrawerCard(Decoration? decoration) {
  return decoration is BoxDecoration && _hasDrawerTopCorners(decoration.borderRadius);
}

bool _shapeIsDrawerCard(ShapeBorder? shape) {
  return shape is RoundedRectangleBorder && _hasDrawerTopCorners(shape.borderRadius);
}

/// Matches the drawer card however it might be rebuilt: a decorated
/// Container or DecoratedBox, or a Material/Card with the same rounded top.
bool _hasRoundedDrawerCard(Widget widget) {
  if (widget is Container) return _decorationIsDrawerCard(widget.decoration);
  if (widget is DecoratedBox) return _decorationIsDrawerCard(widget.decoration);
  if (widget is Material) return _shapeIsDrawerCard(widget.shape);
  if (widget is Card) return _shapeIsDrawerCard(widget.shape);
  return false;
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
    expect(tester.allWidgets.where(_hasRoundedDrawerCard), isEmpty);

    await pump(OnboardingCompleteScreen(onComplete: () {}));
    await tester.pump(const Duration(milliseconds: 300));
    expect(tester.allWidgets.where(_hasRoundedDrawerCard), isEmpty);
  });
}
