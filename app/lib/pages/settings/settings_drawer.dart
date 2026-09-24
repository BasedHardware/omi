import 'dart:io';

import 'package:flutter/material.dart';

import 'package:device_info_plus/device_info_plus.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/models/stt_provider.dart';
import 'package:omi/pages/settings/data_export.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/pages/settings/settings_search_index.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// The Settings sheet: every top-level setting, grouped, plus search over every row in Settings
/// and its pages ([settingsSearchEntries]).
///
/// Everyday settings live here (D4): transcription, conversation display and timeout, Offline
/// Sync, phone calls, home screen, and Data & Privacy (privacy, export, import). Developer
/// Settings keeps only developer tools.
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
  String? _version;
  String? _buildNumber;
  String? _shortDeviceInfo;

  bool _isSearching = false;
  String _searchQuery = '';
  final _searchController = TextEditingController();
  final _searchFocusNode = FocusNode();

  @override
  void initState() {
    super.initState();
    _loadAppAndDeviceInfo();
  }

  @override
  void dispose() {
    _searchController.dispose();
    _searchFocusNode.dispose();
    super.dispose();
  }

  Future<String?> _getShortDeviceInfo() async {
    try {
      final deviceInfoPlugin = DeviceInfoPlugin();
      if (Platform.isAndroid) {
        final androidInfo = await deviceInfoPlugin.androidInfo;
        return '${androidInfo.brand} ${androidInfo.model} — Android ${androidInfo.version.release}';
      } else if (Platform.isIOS) {
        final iosInfo = await deviceInfoPlugin.iosInfo;
        return '${iosInfo.name} — iOS ${iosInfo.systemVersion}';
      }
    } catch (_) {}
    return null;
  }

  Future<void> _loadAppAndDeviceInfo() async {
    try {
      final packageInfo = await PackageInfo.fromPlatform();
      final shortDevice = await _getShortDeviceInfo();
      if (!mounted) return;
      setState(() {
        _version = packageInfo.version;
        _buildNumber = packageInfo.buildNumber;
        _shortDeviceInfo = shortDevice;
      });
    } catch (_) {}
  }

  Future<void> _copyVersionInfo() async {
    final versionPart = _buildNumber != null ? 'Omi AI ${_version ?? ""} ($_buildNumber)' : 'Omi AI ${_version ?? ""}';
    final devicePart = _shortDeviceInfo ?? context.l10n.unknownDevice;
    await OmiClipboard.copy(context, '$versionPart — $devicePart');
  }

  Future<void> _open(SettingsDestination destination) async {
    await openSettingsDestination(context, destination);
    // Row values (plan, transcription provider) may have changed on the page just closed.
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

  Widget _row(
    SettingsDestination destination, {
    required FaIconData icon,
    required String title,
    String? subtitle,
    String? value,
    Widget? tag,
    bool isDestructive = false,
  }) {
    return OmiSettingsRow(
      leading: FaIcon(icon),
      title: title,
      subtitle: subtitle,
      value: value,
      trailing: tag,
      showChevron: !isDestructive,
      isDestructive: isDestructive,
      onTap: () => _open(destination),
    );
  }

  Widget _tag(String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: OmiSpacing.xxs),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.2), borderRadius: OmiRadius.smAll),
      child: Text(label, style: OmiType.caption.copyWith(color: color, fontWeight: FontWeight.w600)),
    );
  }

  String? _planValue(UsageProvider usage) {
    final plan = usage.subscription?.subscription.plan;
    if (plan == null || !plan.isPaid) return null;
    return context.l10n.pro;
  }

  String _transcriptionValue() {
    final prefs = SharedPreferencesUtil();
    return prefs.useCustomStt ? SttProviderConfig.get(prefs.customSttConfig.provider).displayName : 'Omi';
  }

  Widget _buildSettings(BuildContext context) {
    final l10n = context.l10n;
    final deviceConnected = context.select<DeviceProvider, bool>((p) => p.isConnected);
    final planValue = _planValue(context.watch<UsageProvider>());
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        OmiSettingsGroup(
          children: [
            _row(SettingsDestination.profile, icon: FontAwesomeIcons.solidUser, title: l10n.profile),
            _row(SettingsDestination.notifications, icon: FontAwesomeIcons.solidBell, title: l10n.notifications),
            _row(SettingsDestination.planAndUsage,
                icon: FontAwesomeIcons.chartLine, title: l10n.planAndUsage, value: planValue),
            if (deviceConnected)
              _row(SettingsDestination.device, icon: FontAwesomeIcons.bluetooth, title: l10n.deviceSettings),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          header: l10n.conversations,
          children: [
            _row(SettingsDestination.transcription,
                icon: FontAwesomeIcons.microphone, title: l10n.transcription, value: _transcriptionValue()),
            _row(SettingsDestination.conversationDisplay, icon: FontAwesomeIcons.list, title: l10n.conversationDisplay),
            _row(SettingsDestination.conversationTimeout,
                icon: FontAwesomeIcons.clock,
                title: l10n.conversationTimeout,
                subtitle: l10n.setWhenConversationsAutoEnd),
            _row(SettingsDestination.offlineSync, icon: FontAwesomeIcons.solidCloud, title: l10n.offlineSync),
            _row(SettingsDestination.phoneCalls, icon: FontAwesomeIcons.phone, title: l10n.phoneCalls),
            _row(SettingsDestination.homeScreen, icon: FontAwesomeIcons.house, title: l10n.homeScreen),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          header: l10n.dataAndPrivacy,
          children: [
            _row(SettingsDestination.dataPrivacy, icon: FontAwesomeIcons.shield, title: l10n.dataProtection),
            ValueListenableBuilder<bool>(
              valueListenable: DataExport.exportInProgress,
              builder: (context, exporting, _) => OmiSettingsRow(
                leading: const FaIcon(FontAwesomeIcons.fileExport),
                title: l10n.exportAllData,
                subtitle: l10n.exportConversationsToJson,
                trailing: exporting ? const OmiSpinner(size: OmiSpinnerSize.small) : null,
                showChevron: !exporting,
                onTap: exporting ? null : () => _open(SettingsDestination.exportData),
              ),
            ),
            _row(SettingsDestination.importData,
                icon: FontAwesomeIcons.fileImport, title: l10n.importData, subtitle: l10n.importDataFromOtherSources),
            _row(SettingsDestination.permissions, icon: FontAwesomeIcons.shieldHalved, title: l10n.permissions),
            _row(SettingsDestination.integrations,
                icon: FontAwesomeIcons.networkWired, title: l10n.integrations, tag: _tag(l10n.beta, OmiColors.warning)),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          children: [
            if (PlatformService.isIntercomSupported) ...[
              _row(SettingsDestination.feedback, icon: FontAwesomeIcons.solidEnvelope, title: l10n.feedbackBug),
              _row(SettingsDestination.helpCenter, icon: FontAwesomeIcons.book, title: l10n.helpCenter),
            ],
            _row(SettingsDestination.whatsNew, icon: FontAwesomeIcons.solidStar, title: l10n.whatsNew),
            _row(SettingsDestination.referral,
                icon: FontAwesomeIcons.gift, title: l10n.referralProgram, tag: _tag(l10n.newTag, OmiColors.success)),
            _row(SettingsDestination.developer, icon: FontAwesomeIcons.code, title: l10n.developerSettings),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          children: [
            _row(SettingsDestination.signOut,
                icon: FontAwesomeIcons.rightFromBracket, title: l10n.signOut, isDestructive: true),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        _buildVersionInfo(),
        const SizedBox(height: OmiSpacing.xl),
      ],
    );
  }

  Widget _buildVersionInfo() {
    if (!Platform.isIOS && !Platform.isAndroid) return const SizedBox.shrink();
    final displayText = _buildNumber != null ? '${_version ?? ""} ($_buildNumber)' : (_version ?? '');
    return Row(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Text(displayText, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
        OmiIconButton(
          icon: const Icon(Icons.copy, size: 14),
          label: context.l10n.copyToClipboard,
          color: OmiColors.textTertiary,
          onPressed: _copyVersionInfo,
        ),
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
