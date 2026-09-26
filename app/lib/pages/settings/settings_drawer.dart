import 'package:flutter/material.dart';

import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:intl/intl.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/models/subscription.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/pages/settings/settings_groups.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/pages/settings/settings_search_index.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// The Settings sheet (Rev 3 "Account + groups"): the account, the plan and what is left of it,
/// Referral, then the groups (Devices, Recording & Transcription, Notifications & Display, Apps,
/// Integrations, Data & Privacy, Import from other apps, Help & About, Feedback, Developer
/// Settings), plus search over every row in Settings and its pages ([settingsSearchEntries]).
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
    // The colour is read each time the sheet paints, so Settings follows a light/dark switch made
    // on a page opened from it.
    return showOmiModalSheet<void>(
      context: context,
      color: () => OmiColors.surface0,
      shape: const RoundedRectangleBorder(borderRadius: OmiRadius.sheetTop),
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

  @override
  void initState() {
    super.initState();
    _searchFocusNode.addListener(_syncSearching);
  }

  /// Searching while the field has focus or holds text; Cancel shows only then.
  void _syncSearching() {
    final searching = _searchFocusNode.hasFocus || _searchController.text.isNotEmpty;
    if (searching != _isSearching) setState(() => _isSearching = searching);
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

  /// "Signed in with Apple" (or Google) from the account's sign-in provider; the email otherwise.
  static String? _accountSubtitle(AppLocalizations l10n, String email) {
    // No Firebase app in previews and widget tests: there is no provider to name there.
    final providers = Firebase.apps.isEmpty
        ? const <String>[]
        : [...?FirebaseAuth.instance.currentUser?.providerData.map((info) => info.providerId)];
    if (providers.contains('apple.com')) return l10n.signedInWithApple;
    if (providers.contains('google.com')) return l10n.signedInWithGoogle;
    return email.isEmpty ? null : email;
  }

  Widget _buildSettings(BuildContext context) {
    final l10n = context.l10n;
    final subscription = context.watch<UsageProvider>().subscription;
    final prefs = SharedPreferencesUtil();
    final name = prefs.givenName;
    final email = prefs.email;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OmiSettingsGroup(
          children: [
            OmiSettingsRow(
              key: const ValueKey('settings_account'),
              leading: OmiInitialAvatar(name: name.isEmpty ? (email.isEmpty ? l10n.account : email) : name),
              title: name.isEmpty ? l10n.account : name,
              subtitle: _accountSubtitle(l10n, email),
              showChevron: true,
              onTap: () => _open(SettingsDestination.profile),
            ),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        // Plan, referrals and feedback stay one tap from the sheet (David, 2026-09-24).
        _PlanCard(subscription: subscription, onTap: () => _open(SettingsDestination.planAndUsage)),
        const SizedBox(height: OmiSpacing.sm),
        OmiSettingsGroup(
          children: [
            _row(SettingsDestination.referral,
                key: 'settings_row_referral',
                icon: FontAwesomeIcons.gift,
                title: l10n.referralProgram,
                tag: SettingsTag(l10n.newTag, OmiColors.success)),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          children: [
            _row(SettingsDestination.deviceGroup,
                key: 'settings_group_device', icon: FontAwesomeIcons.headphones, title: l10n.devices),
            _row(SettingsDestination.recordingGroup,
                key: 'settings_group_recording',
                icon: FontAwesomeIcons.microphone,
                title: l10n.recordingAndTranscription),
            _row(SettingsDestination.notificationsGroup,
                key: 'settings_group_notifications',
                icon: FontAwesomeIcons.solidBell,
                title: l10n.notificationsAndDisplay),
            _row(SettingsDestination.apps,
                key: 'settings_row_apps', icon: FontAwesomeIcons.tableCellsLarge, title: l10n.apps),
            _row(SettingsDestination.integrations,
                key: 'settings_group_integrations',
                icon: FontAwesomeIcons.networkWired,
                title: l10n.integrations,
                tag: SettingsTag(l10n.beta, OmiColors.warning)),
            _row(SettingsDestination.privacyGroup,
                key: 'settings_group_privacy', icon: FontAwesomeIcons.shield, title: l10n.dataAndPrivacy),
            // Rev 3: bringing recordings over from Plaud, Limitless, Bee… sits at the top level.
            _row(SettingsDestination.importData,
                key: 'settings_row_importData', icon: FontAwesomeIcons.fileImport, title: l10n.importFromOtherApps),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          children: [
            _row(SettingsDestination.helpGroup,
                key: 'settings_group_help', icon: FontAwesomeIcons.circleQuestion, title: l10n.helpAndAbout),
            if (PlatformService.isIntercomSupported)
              _row(SettingsDestination.feedback,
                  key: 'settings_row_feedback', icon: FontAwesomeIcons.solidEnvelope, title: l10n.feedbackBug),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          children: [
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

  /// v2: a large title with the close X on its trailing edge (UX contract §1), then the search
  /// field. The field stays where it is while searching — only Cancel slides in beside it — so the
  /// list under it never moves (IMG_1147); its edges line up with the cards'.
  Widget _buildHeader(BuildContext context) {
    final l10n = context.l10n;
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, 0, OmiSpacing.xxs, 0),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Expanded(
                child: Semantics(
                  header: true,
                  child: Text(l10n.settings, maxLines: 1, overflow: TextOverflow.ellipsis, style: OmiType.largeTitle),
                ),
              ),
              const OmiCloseButton(),
            ],
          ),
          const SizedBox(height: OmiSpacing.sm),
          // One height whether or not Cancel shows, so the rows below never shift.
          Container(
            height: OmiSize.minTap,
            padding: const EdgeInsets.only(right: OmiSpacing.lg - OmiSpacing.xxs),
            child: Row(
              children: [
                Expanded(
                  child: OmiSearchField(
                    key: const Key('settings_search_field'),
                    placeholder: l10n.searchSettings,
                    controller: _searchController,
                    focusNode: _searchFocusNode,
                    onChanged: (value) {
                      setState(() => _searchQuery = value);
                      _syncSearching();
                    },
                  ),
                ),
                AnimatedSize(
                  duration: OmiMotion.of(context).quick,
                  curve: Curves.easeOutCubic,
                  alignment: Alignment.centerLeft,
                  child: _isSearching
                      ? Padding(
                          padding: const EdgeInsets.only(left: OmiSpacing.xs),
                          child: OmiButton.tertiary(
                            key: const Key('settings_search_cancel'),
                            label: l10n.cancel,
                            size: OmiButtonSize.compact,
                            onPressed: _stopSearch,
                          ),
                        )
                      : const SizedBox.shrink(),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        _buildHeader(context),
        const SizedBox(height: OmiSpacing.xs),
        Expanded(
          child: SingleChildScrollView(
            // Room to scroll the last results above the keyboard; nothing above moves.
            padding: EdgeInsets.fromLTRB(OmiSpacing.lg, 0, OmiSpacing.lg, MediaQuery.viewInsetsOf(context).bottom),
            keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
            child:
                _isSearching && _searchQuery.trim().isNotEmpty ? _buildSearchResults(context) : _buildSettings(context),
          ),
        ),
      ],
    );
  }
}

/// The plan at a glance (v2 Settings): which plan, what is left of this month's premium
/// transcription on the free plan, and a bar of it. Opens Plan & Usage.
class _PlanCard extends StatelessWidget {
  const _PlanCard({required this.subscription, required this.onTap});

  final UserSubscriptionResponse? subscription;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final sub = subscription;
    final paid = sub?.subscription.plan.isPaid ?? false;
    final limitSeconds = sub?.transcriptionSecondsLimit ?? 0;
    final metered = sub != null && !paid && limitSeconds > 0;
    final limit = (limitSeconds / 60).round();
    final left = metered ? ((limitSeconds - sub.transcriptionSecondsUsed).clamp(0, limitSeconds) / 60).round() : 0;
    final title = sub == null ? l10n.planAndUsage : (paid ? l10n.pro : l10n.freePlan);
    final subtitle = metered
        ? l10n.premiumMinutesLeftThisMonth(NumberFormat.decimalPattern(l10n.localeName).format(left), limit)
        : null;
    return OmiCard(
      key: const ValueKey('settings_row_planAndUsage'),
      padding: const EdgeInsets.all(OmiSpacing.md),
      onTap: onTap,
      semanticLabel: subtitle == null ? title : '$title, $subtitle',
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              const OmiIconTile(child: FaIcon(FontAwesomeIcons.chartLine, size: 16)),
              const SizedBox(width: OmiSpacing.sm),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(title, style: OmiType.headline),
                    if (subtitle != null) ...[
                      const SizedBox(height: 2),
                      Text(subtitle, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                    ],
                  ],
                ),
              ),
              const SizedBox(width: OmiSpacing.xs),
              OmiGlyph(OmiGlyphs.chevronRight, size: 14, color: OmiColors.textTertiary),
            ],
          ),
          if (metered) ...[
            const SizedBox(height: 10),
            OmiProgressBar(value: limit == 0 ? 0 : left / limit),
          ],
        ],
      ),
    );
  }
}
