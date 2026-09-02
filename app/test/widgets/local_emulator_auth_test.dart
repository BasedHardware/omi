import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/auth.dart';
import 'package:omi/providers/auth_provider.dart';

class _RecordingAuthProvider extends AuthenticationProvider {
  _RecordingAuthProvider() : super(initializeListeners: false);

  int localEmulatorSignInCalls = 0;
  int googleSignInCalls = 0;

  @override
  Future<void> onLocalEmulatorSignIn(Function() onSignIn) async {
    localEmulatorSignInCalls++;
    onSignIn();
  }

  @override
  Future<void> onGoogleSignIn(Function() onSignIn) async {
    googleSignInCalls++;
  }
}

void main() {
  testWidgets('local_dev long-press on Google signs in as Alice without a tap', (tester) async {
    final authProvider = _RecordingAuthProvider();
    addTearDown(authProvider.dispose);
    var signedIn = false;

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
          home: Scaffold(
            body: AuthComponent(onSignIn: () => signedIn = true),
          ),
        ),
      ),
    );
    await tester.pump();

    expect(find.byKey(const Key('googleSignIn')), findsOneWidget);
    expect(find.text('Continue as Alice'), findsNothing);

    await tester.longPress(find.byKey(const Key('googleSignIn')));
    await tester.pump();

    expect(authProvider.localEmulatorSignInCalls, 1);
    expect(authProvider.googleSignInCalls, 0);
    expect(signedIn, isTrue);
  });
}
