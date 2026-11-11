// Session-end screens: the sign-in screen the app returns to when the backend fences a deleted
// account, and the primary-language sheet.
import 'package:flutter_test/flutter_test.dart';
import 'package:provider/provider.dart';

import 'package:omi/mobile/mobile_app.dart';
import 'package:omi/pages/settings/language_selection_dialog.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/services/auth/auth_token_result.dart';
import 'package:omi/ui/components/omi_nav_buttons.dart';

import '../harness.dart';

/// The provider state `AuthenticationProvider` reaches from the session-expired stream when the
/// backend answered `403 account_deletion_in_progress`.
class _DeletedAccountAuthenticationProvider extends AuthenticationProvider {
  _DeletedAccountAuthenticationProvider() : super(initializeListeners: false);

  @override
  bool get requiresReauthentication => true;

  @override
  AuthSessionExpirationReason? get sessionExpirationReason => AuthSessionExpirationReason.accountDeleted;

  @override
  int get sessionExpirationGeneration => 1;

  @override
  bool isSignedIn() => false;
}

final authScenarios = <AuditScenario>[
  AuditScenario(
    id: 'auth-account-deleted-sign-in',
    title: 'Sign-in after the deleted-account fence',
    page: 'lib/mobile/mobile_app.dart (MobileApp)',
    state: 'Session expired with reason accountDeleted (backend 403 account_deletion_in_progress)',
    run: (a) async {
      await a.pump(
        const MobileApp(),
        providers: [
          ChangeNotifierProvider<AuthenticationProvider>(create: (_) => _DeletedAccountAuthenticationProvider()),
        ],
        scaffold: false,
      );
      await a.shot('Returned to sign-in with the account-deletion message');
    },
  ),
  AuditScenario(
    id: 'settings-language-sheet',
    title: 'Primary language sheet, no language saved',
    page: 'lib/pages/settings/language_selection_dialog.dart (LanguageSelectionDialog)',
    state: 'Signed-in fixture account with no primary language saved',
    run: (a) async {
      await a.pumpHost((context) => LanguageSelectionDialog.show(context));
      await a.shot('The sheet with its close button', step: 'open');
      await a.tap(find.byType(OmiCloseButton));
      await a.shot('Closed without saving; Home keeps the default language', step: 'closed');
    },
  ),
];
