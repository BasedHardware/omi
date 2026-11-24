import 'dart:async';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/change_name_widget.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/pages/settings/settings_groups.dart';
import 'package:omi/pages/settings/settings_search_index.dart';
import 'package:omi/providers/auth_provider.dart';
import 'package:omi/services/auth_service.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/auth/sign_in_failure.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Account details and sign-in methods. The Settings sheet's first row opens it.
///
/// The recording, voice and memory rows that used to live here are on the Settings group pages
/// (settings_groups.dart).
class ProfilePage extends StatefulWidget {
  const ProfilePage({super.key});

  @override
  State<ProfilePage> createState() => _ProfilePageState();
}

class _ProfilePageState extends State<ProfilePage> {
  final _prefs = SharedPreferencesUtil();
  _AccountSignInMethod? _linkingMethod;
  ProviderLinkAuthorization? _linkAuthorization;

  @override
  void dispose() {
    _linkAuthorization?.cancel();
    super.dispose();
  }

  Future<void> _open(SettingsDestination destination) async {
    await openSettingsDestination(context, destination);
    if (mounted) setState(() {});
  }

  Future<void> _editName() async {
    PlatformManager.instance.analytics.pageOpened('Profile Change Name');
    await showDialog(context: context, builder: (_) => const ChangeNameWidget());
    if (mounted) setState(() {});
  }

  bool _isCurrentAccount(AuthenticationProvider auth, String ownerUid) =>
      ModalRoute.of(context)?.isCurrent == true &&
      _prefs.uid == ownerUid &&
      auth.user?.uid == ownerUid &&
      !auth.requiresReauthentication;

  Future<void> _addSignInMethod(_AccountSignInMethod method, AuthenticationProvider auth, String ownerUid) async {
    if (!mounted || _linkingMethod != null || auth.loading || !_isCurrentAccount(auth, ownerUid)) return;

    final l10n = context.l10n;
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.accountAddSignInMethod,
      message: l10n.accountAddSignInMethodDetails,
      confirmLabel: l10n.add,
    );
    if (!confirmed || !mounted || auth.loading || !_isCurrentAccount(auth, ownerUid)) return;

    final authorization = ProviderLinkAuthorization();
    setState(() {
      _linkingMethod = method;
      _linkAuthorization = authorization;
    });
    try {
      final result = await switch (method) {
        _AccountSignInMethod.google => auth.linkWithGoogle(expectedOwnerUid: ownerUid, authorization: authorization),
        _AccountSignInMethod.apple => auth.linkWithApple(expectedOwnerUid: ownerUid, authorization: authorization),
      };
      if (mounted && _isCurrentAccount(auth, ownerUid) && result?.destinationUid == ownerUid) {
        OmiFeedback.confirm(context, context.l10n.accountSignInMethodAdded);
      }
    } on ProviderLinkConflict {
      if (mounted && _isCurrentAccount(auth, ownerUid)) {
        unawaited(showOmiAlert(
          context,
          title: context.l10n.accountSignInConflictTitle,
          message: context.l10n.accountSignInConflictDetails,
        ));
      }
    } catch (error) {
      final cancelled =
          isSignInCancellation(error) || (error is FirebaseAuthException && error.code == 'web-context-canceled');
      if (!cancelled && mounted && _isCurrentAccount(auth, ownerUid)) {
        final l10n = context.l10n;
        OmiFeedback.error(
          context,
          method == _AccountSignInMethod.google ? l10n.authFailedToLinkGoogle : l10n.authFailedToLinkApple,
          actionLabel: l10n.tryAgain,
          onAction: () => _addSignInMethod(method, auth, ownerUid),
        );
      }
    } finally {
      if (mounted) {
        setState(() {
          _linkingMethod = null;
          _linkAuthorization = null;
        });
      }
      authorization.dispose();
    }
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final uid = _prefs.uid;
    final truncatedUid = uid.length > 6 ? '${uid.substring(0, 3)}•••••${uid.substring(uid.length - 3)}' : uid;
    final auth = context.watch<AuthenticationProvider?>();
    final user = auth?.user;
    final showSignInMethods = !kIsWeb &&
        (defaultTargetPlatform == TargetPlatform.iOS || defaultTargetPlatform == TargetPlatform.android) &&
        auth != null &&
        !auth.requiresReauthentication &&
        user != null &&
        !user.isAnonymous &&
        user.uid == uid;

    return Scaffold(
      key: const ValueKey('settings_page_account'),
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.account)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.lg, OmiSpacing.lg, OmiSpacing.xxl),
        children: [
          OmiSettingsGroup(
            children: [
              OmiSettingsRow(
                key: const ValueKey('settings_row_name'),
                leading: const FaIcon(FontAwesomeIcons.solidUser),
                title: l10n.name,
                value: _prefs.givenName.isEmpty ? l10n.notSet : _prefs.givenName,
                onTap: _editName,
              ),
              OmiSettingsRow(
                key: const ValueKey('settings_row_email'),
                leading: const FaIcon(FontAwesomeIcons.solidEnvelope),
                title: l10n.email,
                value: _prefs.email.isEmpty ? l10n.notSet : _prefs.email,
              ),
              OmiSettingsRow(
                key: const ValueKey('settings_row_userId'),
                leading: const FaIcon(FontAwesomeIcons.solidClipboard),
                title: l10n.userId,
                value: truncatedUid,
                showChevron: false,
                onTap: () => OmiClipboard.copy(context, uid, what: l10n.userId),
              ),
            ],
          ),
          if (showSignInMethods) ...[
            const SizedBox(height: OmiSpacing.xl),
            OmiSettingsGroup(
              header: l10n.accountSignInMethods,
              children: [
                for (final method in _AccountSignInMethod.values) _signInMethodRow(method, auth, user),
              ],
            ),
          ],
          const SizedBox(height: OmiSpacing.xl),
          OmiSettingsGroup(
            children: [
              OmiSettingsRow(
                key: settingsRowKey(SettingsDestination.signOut),
                leading: const FaIcon(FontAwesomeIcons.rightFromBracket),
                title: l10n.signOut,
                isDestructive: true,
                showChevron: false,
                onTap: () => _open(SettingsDestination.signOut),
              ),
              OmiSettingsRow(
                key: settingsRowKey(SettingsDestination.deleteAccount),
                leading: const FaIcon(FontAwesomeIcons.triangleExclamation),
                title: l10n.deleteAccountTitle,
                isDestructive: true,
                showChevron: true,
                onTap: () => _open(SettingsDestination.deleteAccount),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _signInMethodRow(_AccountSignInMethod method, AuthenticationProvider auth, User user) {
    final authorization = _linkingMethod == method ? _linkAuthorization : null;
    if (authorization != null) {
      return ListenableBuilder(
        listenable: authorization,
        builder: (context, _) => _buildSignInMethodRow(method, auth, user, authorization: authorization),
      );
    }
    return _buildSignInMethodRow(method, auth, user);
  }

  OmiSettingsRow _buildSignInMethodRow(
    _AccountSignInMethod method,
    AuthenticationProvider auth,
    User user, {
    ProviderLinkAuthorization? authorization,
  }) {
    final l10n = context.l10n;
    final linked = user.providerData.any((provider) => provider.providerId == method.providerId);
    final canAdd = !linked && _linkingMethod == null && !auth.loading;
    const spinner = OmiSpinner(size: OmiSpinnerSize.small);
    final isLinking = _linkingMethod == method;
    final progress = isLinking ? Semantics(label: l10n.loading, liveRegion: true, child: spinner) : null;
    final canCancel = authorization?.canCancel == true;
    return OmiSettingsRow(
      key: ValueKey('settings_sign_in_method_${method.name}'),
      leading: canCancel ? progress : FaIcon(method.icon),
      title: method.brandName,
      value: canCancel ? l10n.cancel : (linked ? l10n.connected : l10n.add),
      trailing: canCancel ? null : progress,
      showChevron: canAdd,
      onTap: canCancel ? authorization!.cancel : (canAdd ? () => _addSignInMethod(method, auth, user.uid) : null),
    );
  }
}

enum _AccountSignInMethod {
  google('google.com', 'Google', FontAwesomeIcons.google),
  apple('apple.com', 'Apple', FontAwesomeIcons.apple);

  const _AccountSignInMethod(this.providerId, this.brandName, this.icon);

  final String providerId;
  final String brandName;
  final FaIconData icon;
}
