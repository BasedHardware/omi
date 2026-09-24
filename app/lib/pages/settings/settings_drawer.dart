import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/pages/settings/settings_groups.dart';
import 'package:omi/pages/settings/settings_search_index.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// The Settings sheet: Account, then seven groups (Device, Recording & Transcription,
/// Notifications & Display, Integrations, Privacy & Data, Help & About, Developer Settings), plus
/// search over every row in Settings and its pages ([settingsSearchEntries]).
///
/// Every setting is at most one tap below the sheet: a group row opens its group page
/// (settings_groups.dart), whose rows open the same pages the sheet used to open directly.
/// Developer Settings keeps only developer tools.
class SettingsDrawer extends StatefulWidget {
  const SettingsDrawer({super.key});

  @override
  State<SettingsDrawer> createState() => _SettingsDrawerState();

  /// Opens Settings; resolves when the sheet closes (callers compare settings after that).
  static Future<void> show(BuildContext context) {
    // Settings is a grouped list: surface1 rows on the black page colour, so the sheet itself is
    // surface0 (showOmiSheet paints surface1). Same shell otherwise: OmiSheetScaffold content,
    // framework drag handle, trailing close X.
    final showSheet = showModalBottomSheet<void>; // omi-ux-allow: raw-bottom-sheet -- surface0 grouped sheet
    return showSheet(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      showDragHandle: true,
      backgroundColor: OmiColors.surface0,
      shape: const RoundedRectangleBorder(borderRadius: OmiRadius.sheetTop),
      clipBehavior: Clip.antiAlias,
      builder: (context) => const FractionallySizedBox(heightFactor: 0.92, child: SettingsDrawer()),
    );
  }
}

class _SettingsDrawerState extends State<SettingsDrawer> {
  bool _isSearching = false;
  String _searchQuery = '';
  final _searchController = TextEditingController();
  final _searchFocusNode = FocusNode();

  @override
  void dispose() {
    _searchController.dispose();
    _searchFocusNode.dispose();
    super.dispose();
  }

  Future<void> _open(SettingsDestination destination) async {
    await openSettingsDestination(context, destination);
    // The Account row shows the name, which may have changed on the page just closed.
    if (mounted) setState(() {});
  }

  void _startSearch() {
    setState(() => _isSearching = true);
    Future.microtask(() => _searchFocusNode.requestFocus());
  }

  void _stopSearch() {
    setState(() {
      _isSearching = false;
      _searchQuery = '';
      _searchController.clear();
    });
    _searchFocusNode.unfocus();
  }

  SettingsSearchScope _searchScope(BuildContext context) => SettingsSearchScope(
        deviceConnected: context.read<DeviceProvider>().isConnected,
        supportLinks: PlatformService.isIntercomSupported,
        android: PlatformService.isAndroid,
      );

  // ---------------------------------------------------------------------------------------------
  // Rows

  /// A top-level row; [key] is the widget key a UI harness taps (`settings_account`,
  /// `settings_group_<group>`).
  Widget _row(
    SettingsDestination destination, {
    required String key,
    required FaIconData icon,
    required String title,
    String? subtitle,
    Widget? tag,
  }) {
    return OmiSettingsRow(
      key: ValueKey(key),
      leading: FaIcon(icon),
      title: title,
      subtitle: subtitle,
      trailing: tag,
      showChevron: true,
      onTap: () => _open(destination),
    );
  }

  Widget _buildSettings(BuildContext context) {
    final l10n = context.l10n;
    final prefs = SharedPreferencesUtil();
    final name = prefs.givenName;
    final email = prefs.email;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OmiSettingsGroup(
          children: [
            _row(SettingsDestination.profile,
                key: 'settings_account',
                icon: FontAwesomeIcons.solidUser,
                title: name.isEmpty ? l10n.account : name,
                subtitle: email.isEmpty ? null : email),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          children: [
            _row(SettingsDestination.deviceGroup,
                key: 'settings_group_device', icon: FontAwesomeIcons.bluetooth, title: l10n.device),
            _row(SettingsDestination.recordingGroup,
                key: 'settings_group_recording',
                icon: FontAwesomeIcons.microphone,
                title: l10n.recordingAndTranscription),
            _row(SettingsDestination.notificationsGroup,
                key: 'settings_group_notifications',
                icon: FontAwesomeIcons.solidBell,
                title: l10n.notificationsAndDisplay),
            _row(SettingsDestination.integrations,
                key: 'settings_group_integrations',
                icon: FontAwesomeIcons.networkWired,
                title: l10n.integrations,
                tag: SettingsTag(l10n.beta, OmiColors.warning)),
            _row(SettingsDestination.privacyGroup,
                key: 'settings_group_privacy', icon: FontAwesomeIcons.shield, title: l10n.dataAndPrivacy),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          children: [
            _row(SettingsDestination.helpGroup,
                key: 'settings_group_help', icon: FontAwesomeIcons.circleQuestion, title: l10n.helpAndAbout),
            _row(SettingsDestination.developer,
                key: 'settings_group_developer', icon: FontAwesomeIcons.code, title: l10n.developerSettings),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
      ],
    );
  }

  Widget _buildSearchResults(BuildContext context) {
    final results = searchSettings(context.l10n, _searchQuery, _searchScope(context));
    if (results.isEmpty) {
      return OmiEmptyState(icon: Icons.search, title: context.l10n.noResultsFound);
    }
    return OmiSettingsGroup(
      children: [
        for (final entry in results)
          OmiSettingsRow(
            title: entry.title(context.l10n),
            isDestructive: entry.destination == SettingsDestination.signOut,
            onTap: () => _open(entry.destination),
          ),
      ],
    );
  }

  // ---------------------------------------------------------------------------------------------
  // Header

  Widget _buildHeader(BuildContext context) {
    final l10n = context.l10n;
    if (_isSearching) {
      return Padding(
        key: const ValueKey('search-header'),
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.xs, OmiSpacing.xs),
        child: Row(
          children: [
            Expanded(
              child: OmiSearchField(
                placeholder: l10n.searchSettings,
                controller: _searchController,
                focusNode: _searchFocusNode,
                autofocus: true,
                onChanged: (value) => setState(() => _searchQuery = value),
              ),
            ),
            OmiButton.tertiary(label: l10n.cancel, size: OmiButtonSize.compact, onPressed: _stopSearch),
          ],
        ),
      );
    }
    return Padding(
      key: const ValueKey('normal-header'),
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
      child: Row(
        children: [
          OmiIconButton(icon: const Icon(Icons.search), label: l10n.search, onPressed: _startSearch),
          Expanded(
            child: Semantics(
              header: true,
              child: Text(l10n.settings, textAlign: TextAlign.center, style: OmiType.headline),
            ),
          ),
          const OmiCloseButton(),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final motion = OmiMotion.of(context);
    return Column(
      children: [
        AnimatedSwitcher(duration: motion.quick, child: _buildHeader(context)),
        const SizedBox(height: OmiSpacing.xs),
        Expanded(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg),
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            child:
                _isSearching && _searchQuery.trim().isNotEmpty ? _buildSearchResults(context) : _buildSettings(context),
          ),
        ),
      ],
    );
  }
}
