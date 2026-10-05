import 'package:flutter/material.dart';

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

    return OmiGroupedPage(
      key: const ValueKey('settings_page_account'),
      title: l10n.account,
      body: ListView(
        padding: OmiGroupedPage.padding,
        children: [
          // Who is signed in, as on the Settings profile card.
          Column(
            children: [
              OmiSettingsAvatar(name: _prefs.givenName, size: 80),
              const SizedBox(height: OmiSpacing.sm),
              if (_prefs.givenName.isNotEmpty)
                Text(_prefs.givenName, style: OmiType.title2, textAlign: TextAlign.center),
              if (_prefs.email.isNotEmpty) ...[
                const SizedBox(height: OmiSpacing.xxs),
                Text(_prefs.email,
                    style: OmiType.subhead.copyWith(color: OmiColors.textSecondary), textAlign: TextAlign.center),
              ],
            ],
          ),
          const SizedBox(height: OmiSpacing.xl),
          OmiSettingsGroup(
            children: [
              OmiSettingsRow(
                key: const ValueKey('settings_row_name'),
                title: l10n.name,
                value: _prefs.givenName.isEmpty ? l10n.notSet : _prefs.givenName,
                onTap: _editName,
              ),
              OmiSettingsRow(
                key: const ValueKey('settings_row_email'),
                title: l10n.email,
                value: _prefs.email.isEmpty ? l10n.notSet : _prefs.email,
              ),
              OmiSettingsRow(
                key: const ValueKey('settings_row_userId'),
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
                title: l10n.signOut,
                isDestructive: true,
                showChevron: false,
                onTap: () => _open(SettingsDestination.signOut),
              ),
              OmiSettingsRow(
                key: settingsRowKey(SettingsDestination.deleteAccount),
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
}
