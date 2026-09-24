import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/change_name_widget.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/pages/settings/settings_groups.dart';
import 'package:omi/pages/settings/settings_search_index.dart';
import 'package:omi/providers/usage_provider.dart';
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

  String? _planValue(UsageProvider usage) {
    final plan = usage.subscription?.subscription.plan;
    if (plan == null || !plan.isPaid) return null;
    return context.l10n.pro;
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final uid = _prefs.uid;
    final truncatedUid = uid.length > 6 ? '${uid.substring(0, 3)}•••••${uid.substring(uid.length - 3)}' : uid;
    final planValue = _planValue(context.watch<UsageProvider>());

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
                key: settingsRowKey(SettingsDestination.planAndUsage),
                leading: const FaIcon(FontAwesomeIcons.chartLine),
                title: l10n.planAndUsage,
                value: planValue,
                onTap: () => _open(SettingsDestination.planAndUsage),
              ),
              OmiSettingsRow(
                key: settingsRowKey(SettingsDestination.referral),
                leading: const FaIcon(FontAwesomeIcons.gift),
                title: l10n.referralProgram,
                trailing: SettingsTag(l10n.newTag, OmiColors.success),
                showChevron: true,
                onTap: () => _open(SettingsDestination.referral),
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
  }
}
