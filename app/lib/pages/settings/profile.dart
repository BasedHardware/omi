import 'package:flutter/material.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/change_name_widget.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/pages/settings/settings_groups.dart';
import 'package:omi/pages/settings/settings_search_index.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Account: who you are (name, email), your plan and referrals, your user id, and at the bottom
/// Sign Out and Delete Account. The Settings sheet's first row opens it.
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

  Future<void> _open(SettingsDestination destination) async {
    await openSettingsDestination(context, destination);
    if (mounted) setState(() {});
  }

  Future<void> _editName() async {
    PlatformManager.instance.analytics.pageOpened('Profile Change Name');
    await showDialog(context: context, builder: (_) => const ChangeNameWidget());
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final uid = _prefs.uid;
    final truncatedUid = uid.length > 6 ? '${uid.substring(0, 3)}•••••${uid.substring(uid.length - 3)}' : uid;

    final classic = Scaffold(
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
    return IosNativeSurface(title: l10n.account, fallback: classic, toolbar: [
      NativeRow('account_back', l10n.back, symbol: 'chevron.left', action: (_) {
        Navigator.of(context).pop();
      })
    ], sections: [
      NativeSection('account_identity', [
        NativeRow('account_name', l10n.name,
            subtitle: _prefs.givenName.isEmpty ? l10n.notSet : _prefs.givenName, action: (_) => _editName()),
        NativeRow('account_email', l10n.email,
            kind: 'label', subtitle: _prefs.email.isEmpty ? l10n.notSet : _prefs.email),
        NativeRow('account_uid', l10n.userId,
            subtitle: truncatedUid, action: (_) => OmiClipboard.copy(context, uid, what: l10n.userId)),
      ]),
      NativeSection('account_actions', [
        NativeRow('account_sign_out', l10n.signOut,
            destructive: true, action: (_) => _open(SettingsDestination.signOut)),
        NativeRow('account_delete', l10n.deleteAccountTitle,
            destructive: true, action: (_) => _open(SettingsDestination.deleteAccount)),
      ]),
    ]);
  }
}
