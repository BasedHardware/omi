import 'package:flutter/gestures.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:integration_test/integration_test.dart';
import 'package:sama/flutter_flow/flutter_flow_drop_down.dart';
import 'package:sama/flutter_flow/flutter_flow_icon_button.dart';
import 'package:sama/flutter_flow/flutter_flow_widgets.dart';
import 'package:sama/index.dart';
import 'package:sama/main.dart';
import 'package:sama/flutter_flow/flutter_flow_util.dart';

import 'package:provider/provider.dart';
import 'package:sama/backend/firebase/firebase_config.dart';
import 'package:sama/auth/firebase_auth/auth_util.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:sama/backend/supabase/supabase.dart';

void main() async {
  IntegrationTestWidgetsFlutterBinding.ensureInitialized();

  testWidgets('newTest', (WidgetTester tester) async {
    _overrideOnError();
    await initFirebase();
    await SupaFlow.initialize();
    await authManager.signOut();

    FFAppState.reset();
    final appState = FFAppState();
    await appState.initializePersistedState();

    await FirebaseAuth.instance.signInWithEmailAndPassword(
        email: 'kodjima33+sama@gmail.com', password: '123456');
    await tester.pumpWidget(ChangeNotifierProvider(
      create: (context) => appState,
      child: MyApp(),
    ));

    await tester.tap(find.byKey(ValueKey('UNDEFINED')));
    await tester.pumpAndSettle(Duration(milliseconds: 5000));
    await tester.longPress(find.byKey(ValueKey('UNDEFINED')));
    await tester.pumpAndSettle(Duration(milliseconds: 1000));
    expect(find.text('Useless Memory'), findsWidgets);
  });
}

// There are certain types of errors that can happen during tests but
// should not break the test.
void _overrideOnError() {
  final originalOnError = FlutterError.onError!;
  FlutterError.onError = (errorDetails) {
    if (_shouldIgnoreError(errorDetails.toString())) {
      return;
    }
    originalOnError(errorDetails);
  };
}

bool _shouldIgnoreError(String error) {
  // It can fail to decode some SVGs - this should not break the test.
  if (error.contains('ImageCodecException')) {
    return true;
  }
  // Overflows happen all over the place,
  // but they should not break tests.
  if (error.contains('overflowed by')) {
    return true;
  }
  // Sometimes some images fail to load, it generally does not break the test.
  if (error.contains('No host specified in URI') ||
      error.contains('EXCEPTION CAUGHT BY IMAGE RESOURCE SERVICE')) {
    return true;
  }
  // These errors should be avoided, but they should not break the test.
  if (error.contains('setState() called after dispose()')) {
    return true;
  }

  return false;
}
