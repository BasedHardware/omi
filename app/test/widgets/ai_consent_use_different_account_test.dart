import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/onboarding/ai_consent_widget.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/ui/ui.dart';

class _Auth extends ChangeNotifier implements AuthenticationProvider {
  @override
  void openPrivacyPolicy() {}
  @override
  void openTermsOfService() {}
  @override
  dynamic noSuchMethod(Invocation invocation) => super.noSuchMethod(invocation);
}

void main() {
  testWidgets('data & privacy asks to agree and keeps a way back to a different account', (tester) async {
    var agreed = 0;
    var switched = 0;
    await tester.pumpWidget(ChangeNotifierProvider<AuthenticationProvider>.value(
      value: _Auth(),
      child: MaterialApp(
        theme: buildOmiTheme(),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: const [Locale('en')],
        home: Scaffold(body: AiConsentWidget(onAgree: () => agreed++, onUseDifferentAccount: () => switched++)),
      ),
    ));
    await tester.pump();
    final en = lookupAppLocalizations(const Locale('en'));
    expect(find.text(en.agreeAndContinue), findsOneWidget);
    await tester.tap(find.byKey(const Key('ai_consent_use_different_account')));
    await tester.pump();
    expect(switched, 1);
    expect(agreed, 0);

    await tester.tap(find.byKey(const Key('ai_consent_agree')));
    await tester.pump();
    expect(agreed, 1);
  });
}
