import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/auth.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/services/auth/local_emulator_auth.dart';

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

Future<void> _pumpAuth(WidgetTester tester, _RecordingAuthProvider authProvider,
    {required VoidCallback onSignIn}) async {
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
          body: AuthComponent(onSignIn: onSignIn),
        ),
      ),
    ),
  );
  await tester.pump();
}

void main() {
  testWidgets('a tap on Google does not sign in as Alice', (tester) async {
    final authProvider = _RecordingAuthProvider();
    addTearDown(authProvider.dispose);
    var signedIn = false;

    await _pumpAuth(tester, authProvider, onSignIn: () => signedIn = true);

    expect(find.byKey(const Key('googleSignIn')), findsOneWidget);
    expect(find.text('Continue as Alice'), findsNothing);

    await tester.tap(find.byKey(const Key('googleSignIn')));
    await tester.pump();

    expect(authProvider.localEmulatorSignInCalls, 0);
    expect(authProvider.googleSignInCalls, 1);
    expect(signedIn, isFalse);
  });

  testWidgets('holding Google for 5 seconds signs in as Alice without a tap', (tester) async {
    final authProvider = _RecordingAuthProvider();
    addTearDown(authProvider.dispose);
    var signedIn = false;

    await _pumpAuth(tester, authProvider, onSignIn: () => signedIn = true);

    final gesture = await tester.startGesture(tester.getCenter(find.byKey(const Key('googleSignIn'))));
    await tester.pump(const Duration(seconds: 2));
    expect(authProvider.localEmulatorSignInCalls, 0);
    await tester.pump(const Duration(seconds: 2));
    expect(authProvider.localEmulatorSignInCalls, 0);

    await tester.pump(kLocalEmulatorSignInHoldDuration - const Duration(seconds: 4));
    await tester.pump();

    expect(authProvider.localEmulatorSignInCalls, 1);
    expect(authProvider.googleSignInCalls, 0);
    expect(signedIn, isTrue);

    await gesture.up();
    await tester.pump();
    expect(authProvider.googleSignInCalls, 0);
  });

  testWidgets('Google sign-in has no Material splash or press overlay', (tester) async {
    final authProvider = _RecordingAuthProvider();
    addTearDown(authProvider.dispose);

    await _pumpAuth(tester, authProvider, onSignIn: () {});

    expect(find.byType(ElevatedButton), findsNothing);
    expect(find.byType(InkWell), findsNothing);
    expect(find.byType(InkResponse), findsNothing);
  });

  testWidgets('releasing Google before 5 seconds does not sign in as Alice', (tester) async {
    final authProvider = _RecordingAuthProvider();
    addTearDown(authProvider.dispose);
    var signedIn = false;

    await _pumpAuth(tester, authProvider, onSignIn: () => signedIn = true);

    final gesture = await tester.startGesture(tester.getCenter(find.byKey(const Key('googleSignIn'))));
    await tester.pump(const Duration(seconds: 2));
    await gesture.up();
    await tester.pump();
    await tester.pump(kLocalEmulatorSignInHoldDuration);

    expect(authProvider.localEmulatorSignInCalls, 0);
    expect(signedIn, isFalse);
  });
}
