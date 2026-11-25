import 'dart:async';

import 'package:flutter/material.dart';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/pages/settings/profile.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';

import '../../helpers/account_sign_in_fixture.dart';

Finder _providerRow(String method) => find.byKey(ValueKey('settings_sign_in_method_$method'));

Finder _dialogAction(String label) => find.descendant(of: find.byType(OmiAlertDialog), matching: find.text(label));

Future<void> _openConfirmation(WidgetTester tester, {String method = 'google'}) async {
  await tester.dragUntilVisible(_providerRow(method).hitTestable(), find.byType(ListView), const Offset(0, -100));
  await tester.pumpAndSettle();
  await tester.tap(_providerRow(method));
  await tester.pumpAndSettle();
}

Future<void> _confirm(WidgetTester tester) async {
  await tester.tap(_dialogAction('Add'));
  await tester.pump();
}

Future<void> _pumpAccount(
  WidgetTester tester,
  AccountSignInFixture fixture, {
  TargetPlatform platform = TargetPlatform.iOS,
  Size size = const Size(390, 844),
  double textScale = 1,
}) async {
  tester.view.physicalSize = size;
  tester.view.devicePixelRatio = 1;
  tester.platformDispatcher.textScaleFactorTestValue = textScale;
  addTearDown(tester.view.reset);
  addTearDown(tester.platformDispatcher.clearTextScaleFactorTestValue);
  addTearDown(fixture.dispose);
  await tester.pumpWidget(
    ChangeNotifierProvider<AuthenticationProvider>.value(
      value: fixture,
      child: MaterialApp(
        theme: buildOmiTheme(brightness: Brightness.light).copyWith(platform: platform),
        localizationsDelegates: AppLocalizations.localizationsDelegates,
        supportedLocales: AppLocalizations.supportedLocales,
        locale: const Locale('en'),
        home: const ProfilePage(),
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  final l10n = lookupAppLocalizations(const Locale('en'));
  final profile = find.byKey(const ValueKey('settings_page_account'));

  setUp(() async {
    SharedPreferences.setMockInitialValues(AccountSignInFixture.profile);
    await SharedPreferencesUtil.init();
  });

  testWidgets('requires confirmation before starting provider sign-in', (tester) async {
    final fixture = AccountSignInFixture();
    await _pumpAccount(tester, fixture);

    expect(find.text(l10n.accountSignInMethods), findsOneWidget);
    expect(find.descendant(of: _providerRow('apple'), matching: find.text(l10n.connected)), findsOneWidget);
    expect(tester.widget<OmiSettingsRow>(_providerRow('apple')).onTap, isNull);

    await _openConfirmation(tester);
    expect(find.text(l10n.accountAddSignInMethodDetails), findsOneWidget);
    expect(fixture.linkAttempts, isEmpty);

    await tester.tap(_dialogAction(l10n.cancel));
    await tester.pumpAndSettle();
    expect(fixture.linkAttempts, isEmpty);
    expect(profile, findsOneWidget);
    expect(_providerRow('google').hitTestable(), findsOneWidget);
  });

  for (final (current, selected, platform, size, zoom) in [
    ('apple.com', 'google', TargetPlatform.iOS, const Size(320, 568), 1.8),
    ('google.com', 'apple', TargetPlatform.android, const Size(390, 844), 1.0),
  ]) {
    testWidgets('keeps the account and explains an occupied $selected sign-in', (tester) async {
      final pending = Completer<ProviderLinkResult?>();
      final fixture = AccountSignInFixture(providerId: current)..onLink = (providerId, _) => pending.future;
      await _pumpAccount(tester, fixture, platform: platform, size: size, textScale: zoom);

      await _openConfirmation(tester, method: selected);
      await _confirm(tester);
      await tester.pump(const Duration(milliseconds: 300));

      expect(fixture.linkAttempts, [(selected == 'google' ? 'google.com' : 'apple.com', AccountSignInFixture.uid)]);
      expect(find.descendant(of: _providerRow(selected), matching: find.byType(OmiSpinner)), findsOneWidget);
      final progressRow = tester.widget<OmiSettingsRow>(_providerRow(selected));
      expect(progressRow.value, l10n.cancel);
      expect(progressRow.onTap, isNotNull);

      pending.completeError(const ProviderLinkConflict());
      await tester.pumpAndSettle();
      expect(find.text(l10n.accountSignInConflictTitle), findsOneWidget);
      expect(find.text(l10n.accountSignInConflictDetails), findsOneWidget);
      expect(tester.takeException(), isNull);

      await tester.ensureVisible(_dialogAction(l10n.ok));
      await tester.tap(_dialogAction(l10n.ok));
      await tester.pumpAndSettle();
      expect(profile, findsOneWidget);
      expect(fixture.user?.uid, AccountSignInFixture.uid);
      expect(fixture.user?.providerData.single.providerId, current);
      expect(tester.widget<OmiSettingsRow>(_providerRow(selected)).onTap, isNotNull);
    });
  }

  testWidgets('shows the newly connected provider and retains the account', (tester) async {
    final fixture = AccountSignInFixture();
    fixture.onLink = (providerId, _) async {
      fixture.updateUser(AccountSignInFixture.uid, ['apple.com', providerId]);
      return const ProviderLinkResult(destinationUid: AccountSignInFixture.uid);
    };
    await _pumpAccount(tester, fixture);

    await _openConfirmation(tester);
    await _confirm(tester);
    await tester.pumpAndSettle();

    expect(profile, findsOneWidget);
    expect(find.descendant(of: _providerRow('google'), matching: find.text(l10n.connected)), findsOneWidget);
    expect(find.text(l10n.accountSignInMethodAdded), findsOneWidget);
    expect(fixture.user?.uid, AccountSignInFixture.uid);
  });

  testWidgets('can retry after a provider error and cancel the next provider prompt', (tester) async {
    var firstAttempt = true;
    final fixture = AccountSignInFixture()
      ..onLink = (providerId, _) async {
        if (firstAttempt) {
          firstAttempt = false;
          throw FirebaseAuthException(code: 'network-request-failed');
        }
        return null;
      };
    await _pumpAccount(tester, fixture);

    await _openConfirmation(tester);
    await _confirm(tester);
    await tester.pumpAndSettle();
    expect(find.text(l10n.authFailedToLinkGoogle), findsOneWidget);

    await tester.tap(find.text(l10n.tryAgain));
    await tester.pumpAndSettle();
    expect(find.text(l10n.accountAddSignInMethod), findsOneWidget);
    await _confirm(tester);
    await tester.pumpAndSettle();

    expect(fixture.linkAttempts, [('google.com', AccountSignInFixture.uid), ('google.com', AccountSignInFixture.uid)]);
    expect(profile, findsOneWidget);
    expect(find.byType(SnackBar), findsNothing);
    expect(_providerRow('google').hitTestable(), findsOneWidget);
  });

  testWidgets('can cancel Google authorization after returning to the account page', (tester) async {
    final pending = Completer<ProviderLinkResult?>();
    final fixture = AccountSignInFixture()
      ..onLink = (_, authorization) {
        final attempt = authorization!;
        attempt.addListener(() {
          if (!attempt.canCancel) pending.complete(null);
        });
        return pending.future;
      };
    await _pumpAccount(tester, fixture);

    await _openConfirmation(tester);
    await _confirm(tester);
    await tester.pump(const Duration(milliseconds: 300));

    final cancel = find.descendant(of: _providerRow('google'), matching: find.text(l10n.cancel));
    expect(cancel.hitTestable(), findsOneWidget);
    await tester.tap(cancel);
    await tester.pumpAndSettle();

    expect(find.byType(OmiAlertDialog), findsNothing);
    expect(find.byType(SnackBar), findsNothing);
    expect(tester.widget<OmiSettingsRow>(_providerRow('google')).value, l10n.add);
    expect(fixture.user?.uid, AccountSignInFixture.uid);
  });

  testWidgets('discards a late provider collision after the account changes', (tester) async {
    final pending = Completer<ProviderLinkResult?>();
    final fixture = AccountSignInFixture()..onLink = (providerId, _) => pending.future;
    await _pumpAccount(tester, fixture);

    await _openConfirmation(tester);
    await _confirm(tester);
    await tester.pump(const Duration(milliseconds: 300));
    fixture.updateUser('another-account', ['google.com']);
    pending.completeError(const ProviderLinkConflict());
    await tester.pumpAndSettle();

    expect(fixture.linkAttempts, [('google.com', AccountSignInFixture.uid)]);
    expect(find.byType(OmiAlertDialog), findsNothing);
    expect(find.text(l10n.accountSignInMethods), findsNothing);
    expect(fixture.user?.uid, 'another-account');
  });
}
