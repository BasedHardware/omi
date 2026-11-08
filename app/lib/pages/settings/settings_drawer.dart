import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/settings_groups.dart';
import 'package:omi/pages/settings/widgets/plans/plan_display_name.dart';
import 'package:omi/pages/settings/widgets/settings_plan_section.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/pages/settings/settings_search_index.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// The Settings sheet: Account and Plan, then the groups people open most (Device, Recording &
/// Transcription, Notifications & Display, Data & Privacy), Voice, Integrations, Memories, Goals,
/// Help & About and Developer Settings, plus search over every row in Settings and its pages
/// ([settingsSearchEntries]).
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
    // Settings is a grouped list: surface1 rows on the page colour, so the sheet itself is surface0
    // (showOmiSheet paints surface1). Same shell otherwise, minus the handle band: its own header
    // with a trailing close X. The surface is read on every rebuild, so switching Light/Dark from a page
    // opened here repaints the sheet too.
    return showOmiSurfaceSheet<void>(
      context: context,
      surface: () => OmiColors.surface0,
      // No handle band: the header (with its close X) is the top of the sheet, which still swipes
      // down to close.
      showDragHandle: false,
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
        rememberedDevice: context.read<DeviceProvider>().hasRememberedDevice,
      );

  // ---------------------------------------------------------------------------------------------
  // Rows

  /// A top-level row; [key] is the widget key a UI harness taps (`settings_row_<row>`,
  /// `settings_group_<group>`).
  Widget _row(
    SettingsDestination destination, {
    required String key,
    required FaIconData icon,
    required String title,
    String? subtitle,
    String? value,
    Widget? tag,
  }) {
    return OmiSettingsRow(
      key: ValueKey(key),
      leading: FaIcon(icon),
      title: title,
      subtitle: subtitle,
      value: value,
      trailing: tag,
      showChevron: true,
      onTap: () => _open(destination),
    );
  }

  /// The plan on the Plan & Usage row: "Free Plan" and the Plus plan name (their section adds an
  /// Upgrade button), "Pro" for the other paid plans.
  String? _planValue(UsageProvider usage) {
    final subscription = usage.subscription;
    final plan = subscription?.subscription.plan;
    if (plan == null) return null;
    if (usage.showSubscriptionUI && (plan == PlanType.basic || plan == PlanType.plus)) {
      return planDisplayName(plan, subscription!.availablePlans, context.l10n);
    }
    if (!plan.isPaid) return null;
    return currentPlanDisplayName(context, subscription);
  }

  /// The device on the Device row: its battery when it reports one, else Connected / Disconnected.
  String _deviceValue(DeviceProvider device) {
    if (!device.isConnected) return context.l10n.disconnected;
    final battery = device.batteryLevel;
    return battery >= 0 ? '$battery%' : context.l10n.connected;
  }

  /// Free readers who can still start a trial get Pocket's Upgrade row above Plan & Usage.
  bool _showUpgradeRow(UsageProvider usage) {
    final subscription = usage.subscription;
    if (subscription == null || subscription.subscription.plan.isPaid) return false;
    if (subscription.trialEligible != true) return false;
    return usage.showSubscriptionUI;
  }

  Widget _buildSettings(BuildContext context) {
    final l10n = context.l10n;
    final usage = context.watch<UsageProvider>();
    final planValue = _planValue(usage);
    final showUpgrade = _showUpgradeRow(usage);
    final prefs = SharedPreferencesUtil();
    final name = prefs.givenName;
    final email = prefs.email;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OmiSettingsGroup(
          children: [
            _AccountHeader(
              key: const ValueKey('settings_account'),
              name: name.isEmpty ? l10n.account : name,
              email: email.isEmpty ? null : email,
              onTap: () => _open(SettingsDestination.profile),
            ),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        // Plan stays one tap from the sheet (David, 2026-09-24); for Free and Plus it is a plan card
        // with the minutes meter and the Upgrade button.
        OmiSettingsGroup(
          children: [
            if (showUpgrade)
              _row(
                SettingsDestination.upgrade,
                key: 'settings_row_upgrade',
                icon: FontAwesomeIcons.crown,
                title: l10n.upgrade,
                subtitle: l10n.settingsUpgradeTrialSubtitle(7),
              ),
            SettingsPlanSection(
              planName: planValue,
              onOpen: () => _open(SettingsDestination.planAndUsage),
              row: _row(
                SettingsDestination.planAndUsage,
                key: 'settings_row_planAndUsage',
                icon: FontAwesomeIcons.chartLine,
                title: l10n.planAndUsage,
                value: planValue,
              ),
            ),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        // The groups people open most come first: Device and Recording & Transcription are most of
        // the visits to Settings, then Notifications & Display and Data & Privacy.
        OmiSettingsGroup(
          children: [
            _row(
              SettingsDestination.deviceGroup,
              key: 'settings_group_device',
              icon: FontAwesomeIcons.bluetooth,
              title: l10n.device,
              value: _deviceValue(context.watch<DeviceProvider>()),
            ),
            _row(
              SettingsDestination.recordingGroup,
              key: 'settings_group_recording',
              icon: FontAwesomeIcons.microphone,
              title: l10n.recordingAndTranscription,
            ),
            _row(
              SettingsDestination.notificationsGroup,
              key: 'settings_group_notifications',
              icon: FontAwesomeIcons.solidBell,
              title: l10n.notificationsAndDisplay,
            ),
            _row(
              SettingsDestination.privacyGroup,
              key: 'settings_group_privacy',
              icon: FontAwesomeIcons.shield,
              title: l10n.dataAndPrivacy,
            ),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          children: [
            _row(
              SettingsDestination.voice,
              key: 'settings_group_voice',
              icon: FontAwesomeIcons.volumeHigh,
              title: l10n.assistantVoiceSettingsTitle,
            ),
            _row(
              SettingsDestination.integrations,
              key: 'settings_group_integrations',
              icon: FontAwesomeIcons.networkWired,
              title: l10n.integrations,
              tag: SettingsTag(l10n.beta, OmiColors.warning),
            ),
            _row(
              SettingsDestination.connectAgent,
              key: 'settings_row_connect_agent',
              icon: FontAwesomeIcons.terminal,
              title: l10n.connectAnAgent,
            ),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        // Memories and Goals left the Home tabs (David, 2026-09-29): one tap from the sheet.
        OmiSettingsGroup(
          children: [
            _row(
              SettingsDestination.memories,
              key: 'settings_row_memories',
              icon: FontAwesomeIcons.brain,
              title: l10n.memories,
            ),
            _row(
              SettingsDestination.goals,
              key: 'settings_row_goals',
              icon: FontAwesomeIcons.bullseye,
              title: l10n.goals,
            ),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        // Referrals and feedback stay one tap from the sheet (David, 2026-09-24).
        OmiSettingsGroup(
          children: [
            _row(
              SettingsDestination.helpGroup,
              key: 'settings_group_help',
              icon: FontAwesomeIcons.circleQuestion,
              title: l10n.helpAndAbout,
            ),
            _row(
              SettingsDestination.referral,
              key: 'settings_row_referral',
              icon: FontAwesomeIcons.gift,
              title: l10n.referralProgram,
            ),
            if (PlatformService.isIntercomSupported)
              _row(
                SettingsDestination.feedback,
                key: 'settings_row_feedback',
                icon: FontAwesomeIcons.solidEnvelope,
                title: l10n.feedbackBug,
              ),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          children: [
            _row(
              SettingsDestination.developer,
              key: 'settings_group_developer',
              icon: FontAwesomeIcons.code,
              title: l10n.developerSettings,
            ),
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
      // One header height (48 pt) and 20 pt left padding (OmiSpacing.lg) so opening search
      // never shifts the settings rows below it and the field aligns with the cards (#19241).
      return SizedBox(
        key: const ValueKey('search-header'),
        height: 48,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, 0, OmiSpacing.xs, 0),
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
        ),
      );
    }
    return SizedBox(
      key: const ValueKey('normal-header'),
      height: 48,
      child: Padding(
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
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final motion = OmiMotion.of(context);
    return Padding(
      padding: const EdgeInsets.only(top: OmiSpacing.sm),
      child: Column(
        children: [
          AnimatedSwitcher(duration: motion.quick, child: _buildHeader(context)),
          const SizedBox(height: OmiSpacing.xs),
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg),
              keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
              child: _isSearching && _searchQuery.trim().isNotEmpty
                  ? _buildSearchResults(context)
                  : _buildSettings(context),
            ),
          ),
        ],
      ),
    );
  }
}

/// Who is signed in, at the top of the sheet: the name large with the email under it, like the plan
/// card below it. No picture: Omi has no profile photos, so a placeholder would only add noise.
/// Tapping it opens Account.
class _AccountHeader extends StatelessWidget {
  const _AccountHeader({super.key, required this.name, required this.email, required this.onTap});

  final String name;
  final String? email;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return MergeSemantics(
      child: Semantics(
        button: true,
        child: InkWell(
          onTap: onTap,
          child: Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.md, OmiSpacing.md, OmiSpacing.md),
            child: Row(
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(name, style: OmiType.title3, maxLines: 1, overflow: TextOverflow.ellipsis),
                      if (email != null) ...[
                        const SizedBox(height: 2),
                        Text(
                          email!,
                          style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ],
                  ),
                ),
                ExcludeSemantics(child: Icon(Icons.chevron_right, size: 20, color: OmiColors.textTertiary)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
