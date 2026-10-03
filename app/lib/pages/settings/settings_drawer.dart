import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/pages/settings/settings_search_index.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// Settings, a full-screen page pushed from Home: six labelled groups (Account, Recording, Features,
/// Preferences, Support, Developer) of rows that lead with an icon tile, plus search over every row
/// in Settings and its pages ([settingsSearchEntries]).
///
/// Every setting is at most one tap below this page: a group row opens its group page
/// (settings_groups.dart), whose rows open the settings pages themselves. Developer Settings keeps
/// only developer tools.
class SettingsDrawer extends StatefulWidget {
  const SettingsDrawer({super.key});

  @override
  State<SettingsDrawer> createState() => _SettingsDrawerState();

  /// Opens Settings; resolves when the page is popped (callers compare settings after that).
  static Future<void> show(BuildContext context) => routeToPage(context, const SettingsDrawer());
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
    required String title,
    String? subtitle,
    String? value,
  }) {
    return OmiSettingsRow(
      key: ValueKey(key),
      leading: OmiSettingsIconTile(settingsGlyph(destination)),
      title: title,
      subtitle: subtitle,
      value: value,
      showChevron: true,
      onTap: () => _open(destination),
    );
  }

  /// "Pro" on the Plan & Usage row for a paid plan.
  String? _planValue(UsageProvider usage) {
    final plan = usage.subscription?.subscription.plan;
    if (plan == null || !plan.isPaid) return null;
    return context.l10n.pro;
  }

  Widget _buildSettings(BuildContext context) {
    final l10n = context.l10n;
    final planValue = _planValue(context.watch<UsageProvider>());
    final prefs = SharedPreferencesUtil();
    final name = prefs.givenName;
    final email = prefs.email;
    const outlined = OmiSettingsGroupStyle.outlined;
    const gap = SizedBox(height: OmiSpacing.xl);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        // Who is signed in, on a card of its own: avatar, name, email. Opens Account.
        OmiSettingsGroup(
          style: outlined,
          children: [
            OmiSettingsRow(
              key: const ValueKey('settings_account'),
              leading: OmiSettingsAvatar(name: name),
              // Name, else the email, else "Profile": never "Account", the label of the group below.
              title: name.isNotEmpty ? name : (email.isNotEmpty ? email : l10n.profile),
              titleStyle: OmiType.title3,
              titleMaxLines: 2,
              subtitle: name.isEmpty || email.isEmpty ? null : email,
              subtitleMaxLines: 1,
              showChevron: true,
              onTap: () => _open(SettingsDestination.profile),
            ),
          ],
        ),
        gap,
        // Plan and referrals stay one tap from Settings (David, 2026-09-24).
        OmiSettingsGroup(
          style: outlined,
          header: l10n.account,
          children: [
            _row(SettingsDestination.planAndUsage,
                key: 'settings_row_planAndUsage', title: l10n.planAndUsage, value: planValue),
            _row(SettingsDestination.referral, key: 'settings_row_referral', title: l10n.referralProgram),
          ],
        ),
        gap,
        OmiSettingsGroup(
          style: outlined,
          header: l10n.settingsSectionRecording,
          children: [
            _row(SettingsDestination.deviceGroup, key: 'settings_group_device', title: l10n.device),
            _row(SettingsDestination.recordingGroup,
                key: 'settings_group_recording', title: l10n.recordingAndTranscription),
          ],
        ),
        gap,
        // Memories and Goals left the Home tabs (David, 2026-09-29): one tap from Settings.
        OmiSettingsGroup(
          style: outlined,
          header: l10n.features,
          children: [
            _row(SettingsDestination.memories, key: 'settings_row_memories', title: l10n.memories),
            _row(SettingsDestination.goals, key: 'settings_row_goals', title: l10n.goals),
            _row(SettingsDestination.integrations, key: 'settings_group_integrations', title: l10n.integrations),
          ],
        ),
        gap,
        OmiSettingsGroup(
          style: outlined,
          header: l10n.preferences,
          children: [
            _row(SettingsDestination.notificationsGroup,
                key: 'settings_group_notifications', title: l10n.notificationsAndDisplay),
            _row(SettingsDestination.privacyGroup, key: 'settings_group_privacy', title: l10n.dataAndPrivacy),
          ],
        ),
        gap,
        OmiSettingsGroup(
          style: outlined,
          header: l10n.settingsSectionSupport,
          children: [
            _row(SettingsDestination.helpGroup, key: 'settings_group_help', title: l10n.helpAndAbout),
            if (PlatformService.isIntercomSupported)
              _row(SettingsDestination.feedback, key: 'settings_row_feedback', title: l10n.feedbackBug),
          ],
        ),
        gap,
        OmiSettingsGroup(
          style: outlined,
          header: l10n.developer,
          children: [
            _row(SettingsDestination.developer, key: 'settings_group_developer', title: l10n.developerSettings),
          ],
        ),
        gap,
      ],
    );
  }

  Widget _buildSearchResults(BuildContext context) {
    final results = searchSettings(context.l10n, _searchQuery, _searchScope(context));
    if (results.isEmpty) {
      return OmiEmptyState(icon: Icons.search, title: context.l10n.noResultsFound);
    }
    return OmiSettingsGroup(
      style: OmiSettingsGroupStyle.outlined,
      children: [
        for (final entry in results) _searchResultRow(context, entry),
      ],
    );
  }

  Widget _searchResultRow(BuildContext context, SettingsSearchEntry entry) {
    // Sign out reads red here too, as it does on Account: title and glyph.
    final destructive = entry.destination == SettingsDestination.signOut;
    final glyph = settingsGlyph(entry.destination);
    return OmiSettingsRow(
      leading: destructive
          ? OmiSettingsIconTile.custom(child: OmiLineIcon(glyph, color: OmiColors.danger))
          : OmiSettingsIconTile(glyph),
      title: entry.title(context.l10n),
      isDestructive: destructive,
      onTap: () => _open(entry.destination),
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
    // A pushed page: back on the leading edge, search trailing, both on the warm tile colour.
    return Padding(
      key: const ValueKey('normal-header'),
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
      child: Row(
        children: [
          OmiBackButton.circled(fillColor: OmiColors.iconTile),
          Expanded(
            child: Semantics(
              header: true,
              child: Text(l10n.settings, textAlign: TextAlign.center, style: OmiType.headline),
            ),
          ),
          OmiIconButton.filled(
            icon: const OmiLineIcon(OmiLineGlyph.search),
            label: l10n.search,
            onPressed: _startSearch,
            fillColor: OmiColors.iconTile,
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final motion = OmiMotion.of(context);
    return OmiSettingsTypeface(
      child: Scaffold(
        backgroundColor: OmiColors.groupedPage,
        body: SafeArea(
          bottom: false,
          child: Column(
            children: [
              AnimatedSwitcher(duration: motion.quick, child: _buildHeader(context)),
              const SizedBox(height: OmiSpacing.sm),
              Expanded(
                child: SingleChildScrollView(
                  padding: EdgeInsets.fromLTRB(
                      OmiSpacing.md, 0, OmiSpacing.md, MediaQuery.paddingOf(context).bottom + OmiSpacing.md),
                  keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
                  child: _isSearching && _searchQuery.trim().isNotEmpty
                      ? _buildSearchResults(context)
                      : _buildSettings(context),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// The icon of the top-level Settings row a destination sits under: the row's own icon, and the
/// icon a search result for anything below that row leads with (Sign out → Account, Language →
/// Recording). Exhaustive, so a new destination has to pick its row.
OmiLineGlyph settingsGlyph(SettingsDestination destination) => switch (destination) {
      SettingsDestination.profile ||
      SettingsDestination.signOut ||
      SettingsDestination.deleteAccount =>
        OmiLineGlyph.person,
      SettingsDestination.planAndUsage => OmiLineGlyph.chart,
      SettingsDestination.referral => OmiLineGlyph.gift,
      SettingsDestination.deviceGroup ||
      SettingsDestination.device ||
      SettingsDestination.offlineSync ||
      SettingsDestination.phoneCalls ||
      SettingsDestination.permissions =>
        OmiLineGlyph.bluetooth,
      SettingsDestination.recordingGroup ||
      SettingsDestination.transcription ||
      SettingsDestination.language ||
      SettingsDestination.customVocabulary ||
      SettingsDestination.voiceProfile ||
      SettingsDestination.people ||
      SettingsDestination.conversationTimeout =>
        OmiLineGlyph.microphone,
      SettingsDestination.memories => OmiLineGlyph.memories,
      SettingsDestination.goals => OmiLineGlyph.goals,
      SettingsDestination.integrations => OmiLineGlyph.integrations,
      SettingsDestination.notificationsGroup ||
      SettingsDestination.notifications ||
      SettingsDestination.conversationDisplay =>
        OmiLineGlyph.bell,
      SettingsDestination.privacyGroup ||
      SettingsDestination.dataPrivacy ||
      SettingsDestination.exportData ||
      SettingsDestination.importData =>
        OmiLineGlyph.shield,
      SettingsDestination.helpGroup ||
      SettingsDestination.helpCenter ||
      SettingsDestination.whatsNew =>
        OmiLineGlyph.help,
      SettingsDestination.feedback => OmiLineGlyph.chat,
      SettingsDestination.developer || SettingsDestination.creatorPayouts => OmiLineGlyph.code,
    };
