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
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/device_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// The Settings group pages. The Settings sheet shows Account, the five groups here, Integrations
/// and Developer Settings; each group row opens one of these pages, which lists the rows that used
/// to sit at the top level (or on Profile) with their behaviour unchanged.
///
/// Every page is opened through [openSettingsDestination], which records "Settings Page Opened"
/// with the group's page name.

/// A small coloured label after a row title ("BETA", "NEW").
class SettingsTag extends StatelessWidget {
  const SettingsTag(this.label, this.color, {super.key});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: OmiSpacing.xxs),
      decoration: BoxDecoration(color: color.withValues(alpha: 0.2), borderRadius: OmiRadius.smAll),
      child: Text(label, style: OmiType.caption.copyWith(color: color, fontWeight: FontWeight.w600)),
    );
  }
}

/// The widget key of the row that opens [destination] on a group page (for UI harnesses).
ValueKey<String> settingsRowKey(SettingsDestination destination) => ValueKey('settings_row_${destination.name}');

/// The shared page shell: back button, title, and grouped rows on the page colour.
class _GroupPage extends StatelessWidget {
  const _GroupPage({required this.pageKey, required this.title, required this.children});

  final String pageKey;
  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      key: ValueKey(pageKey),
      appBar: AppBar(leading: const OmiBackButton(), title: Text(title)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.lg, OmiSpacing.lg, OmiSpacing.xxl),
        children: children,
      ),
    );
  }
}

/// Opening a row from a group page, then redrawing it: row values (transcription provider, voice
/// response) may have changed on the page just closed.
mixin _GroupRows<T extends StatefulWidget> on State<T> {
  Future<void> open(SettingsDestination destination) async {
    await openSettingsDestination(context, destination);
    if (mounted) setState(() {});
  }

  Widget row(
    SettingsDestination destination, {
    required FaIconData icon,
    required String title,
    String? subtitle,
    String? value,
  }) {
    return OmiSettingsRow(
      key: settingsRowKey(destination),
      leading: FaIcon(icon),
      title: title,
      subtitle: subtitle,
      value: value,
      onTap: () => open(destination),
    );
  }
}

// -----------------------------------------------------------------------------------------------
// Device

/// Device: the connected device's settings (only while connected), Offline Sync and Phone Calls.
class DeviceGroupPage extends StatefulWidget {
  const DeviceGroupPage({super.key});

  @override
  State<DeviceGroupPage> createState() => _DeviceGroupPageState();
}

class _DeviceGroupPageState extends State<DeviceGroupPage> with _GroupRows {
  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final deviceConnected = context.select<DeviceProvider, bool>((p) => p.isConnected);
    return _GroupPage(
      pageKey: 'settings_page_device',
      title: l10n.device,
      children: [
        OmiSettingsGroup(
          children: [
            if (deviceConnected)
              row(SettingsDestination.device, icon: FontAwesomeIcons.bluetooth, title: l10n.deviceSettings),
            row(SettingsDestination.offlineSync, icon: FontAwesomeIcons.solidCloud, title: l10n.offlineSync),
            row(SettingsDestination.phoneCalls, icon: FontAwesomeIcons.phone, title: l10n.phoneCalls),
          ],
        ),
      ],
    );
  }
}

// -----------------------------------------------------------------------------------------------
// Recording & Transcription

/// Recording & Transcription: how Omi hears you (provider, language, vocabulary), your voice and
/// the people around you, when conversations end, and the two capture modes.
class RecordingGroupPage extends StatefulWidget {
  const RecordingGroupPage({super.key});

  @override
  State<RecordingGroupPage> createState() => _RecordingGroupPageState();
}

class _RecordingGroupPageState extends State<RecordingGroupPage> with _GroupRows {
  final _prefs = SharedPreferencesUtil();

  String _transcriptionValue() {
    return _prefs.useCustomStt ? SttProviderConfig.get(_prefs.customSttConfig.provider).displayName : 'Omi';
  }

  String _voiceResponseModeLabel(int mode) {
    switch (mode) {
      case 0:
        return context.l10n.voiceResponseOff;
      case 2:
        return context.l10n.voiceResponseAlways;
      case 1:
      default:
        return context.l10n.voiceResponseHeadphonesOnly;
    }
  }

  Future<void> _showVoiceResponseModeSheet() async {
    final current = _prefs.voiceResponseMode;
    final picked = await showOmiSheet<int>(
      context: context,
      title: context.l10n.voiceResponseModeTitle,
      builder: (sheetContext) => OmiSettingsGroup(
        children: [
          for (final mode in const [0, 1, 2])
            OmiSettingsRow(
              title: _voiceResponseModeLabel(mode),
              trailing: mode == current ? const Icon(Icons.check, color: OmiColors.textPrimary, size: 20) : null,
              showChevron: false,
              onTap: () => Navigator.of(sheetContext).pop(mode),
            ),
        ],
      ),
    );
    if (picked == null || picked == current || !mounted) return;
    setState(() => _prefs.voiceResponseMode = picked);
    PlatformManager.instance.analytics.voiceResponseModeChanged(picked);
  }

  Future<void> _setBackgroundMode(bool value) async {
    final accepted = await context.read<CaptureProvider>().setBackgroundModeEnabled(value);
    if (accepted && mounted) setState(() {});
  }

  Future<void> _setTranscribeLater(bool value) async {
    final accepted = await context.read<CaptureProvider>().setBatchMode(value);
    if (!mounted) return;
    if (!accepted) OmiFeedback.error(context, context.l10n.transcribeLaterNote);
    setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final captureProvider = context.watch<CaptureProvider>();
    final backgroundEnabled = _prefs.backgroundModeEnabled;
    final canEnableBackground = captureProvider.hasNativeBackgroundStreamRoute;
    final batchStorageFull = _prefs.getBool('batchStorageFull');

    return _GroupPage(
      pageKey: 'settings_page_recording',
      title: l10n.recordingAndTranscription,
      children: [
        OmiSettingsGroup(
          children: [
            row(SettingsDestination.transcription,
                icon: FontAwesomeIcons.microphone, title: l10n.transcription, value: _transcriptionValue()),
            row(SettingsDestination.language, icon: FontAwesomeIcons.globe, title: l10n.language),
            row(SettingsDestination.customVocabulary, icon: FontAwesomeIcons.book, title: l10n.customVocabulary),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          children: [
            row(SettingsDestination.voiceProfile, icon: FontAwesomeIcons.waveSquare, title: l10n.speechProfile),
            row(SettingsDestination.people, icon: FontAwesomeIcons.users, title: l10n.identifyingOthers),
            OmiSettingsRow(
              key: const ValueKey('settings_row_voiceResponseMode'),
              leading: const FaIcon(FontAwesomeIcons.volumeHigh),
              title: l10n.voiceResponseMode,
              value: _voiceResponseModeLabel(_prefs.voiceResponseMode),
              onTap: _showVoiceResponseModeSheet,
            ),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        OmiSettingsGroup(
          children: [
            row(SettingsDestination.conversationTimeout,
                icon: FontAwesomeIcons.clock,
                title: l10n.conversationTimeout,
                subtitle: l10n.setWhenConversationsAutoEnd),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),

        // Capture modes: two-state settings, so inline switches that apply immediately.
        OmiSectionHeader(l10n.recording, trailing: SettingsTag(l10n.beta, OmiColors.warning)),
        OmiSettingsGroup(
          footer: l10n.transcribeLaterNote,
          children: [
            OmiSettingsRow.toggle(
              key: const ValueKey('settings_row_transcribeLater'),
              leading: const FaIcon(FontAwesomeIcons.floppyDisk),
              title: l10n.transcribeLaterTitle,
              subtitle: batchStorageFull ? l10n.transcribeLaterStorageFull : l10n.transcribeLaterDescription,
              value: _prefs.batchModeEnabled,
              onChanged: _setTranscribeLater,
            ),
            if (PlatformService.isAndroid)
              OmiSettingsRow.toggle(
                key: const ValueKey('settings_row_backgroundMode'),
                leading: const FaIcon(FontAwesomeIcons.towerBroadcast),
                title: l10n.backgroundModeTitle,
                subtitle: canEnableBackground || backgroundEnabled
                    ? l10n.backgroundModeDescription
                    : l10n.backgroundModeUnavailable,
                value: backgroundEnabled,
                onChanged: (backgroundEnabled || canEnableBackground) ? _setBackgroundMode : null,
              ),
          ],
        ),
      ],
    );
  }
}

// -----------------------------------------------------------------------------------------------
// Notifications & Display

/// Notifications & Display: notifications, the home screen and how conversations are listed.
class NotificationsDisplayGroupPage extends StatefulWidget {
  const NotificationsDisplayGroupPage({super.key});

  @override
  State<NotificationsDisplayGroupPage> createState() => _NotificationsDisplayGroupPageState();
}

class _NotificationsDisplayGroupPageState extends State<NotificationsDisplayGroupPage> with _GroupRows {
  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return _GroupPage(
      pageKey: 'settings_page_notifications',
      title: l10n.notificationsAndDisplay,
      children: [
        OmiSettingsGroup(
          children: [
            row(SettingsDestination.notifications, icon: FontAwesomeIcons.solidBell, title: l10n.notifications),
            row(SettingsDestination.homeScreen, icon: FontAwesomeIcons.house, title: l10n.homeScreen),
            row(SettingsDestination.conversationDisplay, icon: FontAwesomeIcons.list, title: l10n.conversationDisplay),
          ],
        ),
      ],
    );
  }
}

// -----------------------------------------------------------------------------------------------
// Privacy & Data

/// Privacy & Data: data protection, memories, permissions, and exporting or importing data.
class PrivacyDataGroupPage extends StatefulWidget {
  const PrivacyDataGroupPage({super.key});

  @override
  State<PrivacyDataGroupPage> createState() => _PrivacyDataGroupPageState();
}

class _PrivacyDataGroupPageState extends State<PrivacyDataGroupPage> with _GroupRows {
  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return _GroupPage(
      pageKey: 'settings_page_privacy',
      title: l10n.dataAndPrivacy,
      children: [
        OmiSettingsGroup(
          children: [
            row(SettingsDestination.dataPrivacy, icon: FontAwesomeIcons.shield, title: l10n.dataProtection),
            row(SettingsDestination.memories, icon: FontAwesomeIcons.brain, title: l10n.memories),
            row(SettingsDestination.permissions, icon: FontAwesomeIcons.shieldHalved, title: l10n.permissions),
            ValueListenableBuilder<bool>(
              valueListenable: DataExport.exportInProgress,
              builder: (context, exporting, _) => OmiSettingsRow(
                key: settingsRowKey(SettingsDestination.exportData),
                leading: const FaIcon(FontAwesomeIcons.fileExport),
                title: l10n.exportAllData,
                subtitle: l10n.exportConversationsToJson,
                trailing: exporting ? const OmiSpinner(size: OmiSpinnerSize.small) : null,
                showChevron: !exporting,
                onTap: exporting ? null : () => open(SettingsDestination.exportData),
              ),
            ),
            row(SettingsDestination.importData,
                icon: FontAwesomeIcons.fileImport, title: l10n.importData, subtitle: l10n.importDataFromOtherSources),
          ],
        ),
      ],
    );
  }
}

// -----------------------------------------------------------------------------------------------
// Help & About

/// Help & About: feedback and the help center (where Intercom is supported), What's New, and the
/// app version with a copy button.
class HelpAboutGroupPage extends StatefulWidget {
  const HelpAboutGroupPage({super.key});

  @override
  State<HelpAboutGroupPage> createState() => _HelpAboutGroupPageState();
}

class _HelpAboutGroupPageState extends State<HelpAboutGroupPage> with _GroupRows {
  String? _version;
  String? _buildNumber;
  String? _shortDeviceInfo;

  @override
  void initState() {
    super.initState();
    _loadAppAndDeviceInfo();
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

  Widget _buildVersionInfo() {
    if (!Platform.isIOS && !Platform.isAndroid) return const SizedBox.shrink();
    final displayText = _buildNumber != null ? '${_version ?? ""} ($_buildNumber)' : (_version ?? '');
    return Row(
      key: const ValueKey('settings_row_version'),
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

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return _GroupPage(
      pageKey: 'settings_page_help',
      title: l10n.helpAndAbout,
      children: [
        OmiSettingsGroup(
          children: [
            if (PlatformService.isIntercomSupported) ...[
              row(SettingsDestination.feedback, icon: FontAwesomeIcons.solidEnvelope, title: l10n.feedbackBug),
              row(SettingsDestination.helpCenter, icon: FontAwesomeIcons.book, title: l10n.helpCenter),
            ],
            row(SettingsDestination.whatsNew, icon: FontAwesomeIcons.solidStar, title: l10n.whatsNew),
          ],
        ),
        const SizedBox(height: OmiSpacing.xl),
        _buildVersionInfo(),
      ],
    );
  }
}
