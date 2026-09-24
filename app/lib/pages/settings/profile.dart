import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/settings/change_name_widget.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/pages/settings/settings_search_index.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/platform/platform_service.dart';

/// Profile: who you are (name, email, language, vocabulary, memories), your voice (one Voice
/// Profile entry, people, voice responses, capture modes) and the account (user id, delete).
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

  Future<void> _editName() async {
    PlatformManager.instance.analytics.pageOpened('Profile Change Name');
    await showDialog(context: context, builder: (_) => const ChangeNameWidget());
    if (mounted) setState(() {});
  }

  Widget _betaTag() {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xs, vertical: OmiSpacing.xxs),
      decoration: BoxDecoration(color: OmiColors.warning.withValues(alpha: 0.2), borderRadius: OmiRadius.smAll),
      child: Text(
        context.l10n.beta,
        style: OmiType.caption.copyWith(color: OmiColors.warning, fontWeight: FontWeight.w600),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final uid = _prefs.uid;
    final truncatedUid = uid.length > 6 ? '${uid.substring(0, 3)}•••••${uid.substring(uid.length - 3)}' : uid;
    final captureProvider = context.watch<CaptureProvider>();
    final backgroundEnabled = _prefs.backgroundModeEnabled;
    final canEnableBackground = captureProvider.hasNativeBackgroundStreamRoute;
    final batchStorageFull = _prefs.getBool('batchStorageFull');

    return Scaffold(
      appBar: AppBar(leading: const OmiBackButton(), title: Text(l10n.profile)),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.lg, OmiSpacing.lg, OmiSpacing.xxl),
        children: [
          // You
          OmiSettingsGroup(
            children: [
              OmiSettingsRow(
                leading: const FaIcon(FontAwesomeIcons.solidUser),
                title: l10n.name,
                value: _prefs.givenName.isEmpty ? l10n.notSet : _prefs.givenName,
                onTap: _editName,
              ),
              OmiSettingsRow(
                leading: const FaIcon(FontAwesomeIcons.solidEnvelope),
                title: l10n.email,
                value: _prefs.email.isEmpty ? l10n.notSet : _prefs.email,
              ),
              OmiSettingsRow(
                leading: const FaIcon(FontAwesomeIcons.globe),
                title: l10n.language,
                onTap: () => _open(SettingsDestination.language),
              ),
              OmiSettingsRow(
                leading: const FaIcon(FontAwesomeIcons.book),
                title: l10n.customVocabulary,
                onTap: () => _open(SettingsDestination.customVocabulary),
              ),
              OmiSettingsRow(
                leading: const FaIcon(FontAwesomeIcons.brain),
                title: l10n.memories,
                onTap: () => _open(SettingsDestination.memories),
              ),
            ],
          ),
          const SizedBox(height: OmiSpacing.xl),

          // Voice & people
          OmiSettingsGroup(
            children: [
              OmiSettingsRow(
                leading: const FaIcon(FontAwesomeIcons.microphone),
                title: l10n.speechProfile,
                onTap: () => _open(SettingsDestination.voiceProfile),
              ),
              OmiSettingsRow(
                leading: const FaIcon(FontAwesomeIcons.users),
                title: l10n.identifyingOthers,
                onTap: () => _open(SettingsDestination.people),
              ),
              OmiSettingsRow(
                leading: const FaIcon(FontAwesomeIcons.volumeHigh),
                title: l10n.voiceResponseMode,
                value: _voiceResponseModeLabel(_prefs.voiceResponseMode),
                onTap: _showVoiceResponseModeSheet,
              ),
            ],
          ),
          const SizedBox(height: OmiSpacing.xl),

          // Capture modes: two-state settings, so inline switches that apply immediately.
          OmiSectionHeader(l10n.recording, trailing: _betaTag()),
          OmiSettingsGroup(
            footer: l10n.transcribeLaterNote,
            children: [
              if (PlatformService.isAndroid)
                OmiSettingsRow.toggle(
                  leading: const FaIcon(FontAwesomeIcons.towerBroadcast),
                  title: l10n.backgroundModeTitle,
                  subtitle: canEnableBackground || backgroundEnabled
                      ? l10n.backgroundModeDescription
                      : l10n.backgroundModeUnavailable,
                  value: backgroundEnabled,
                  onChanged: (backgroundEnabled || canEnableBackground) ? _setBackgroundMode : null,
                ),
              OmiSettingsRow.toggle(
                leading: const FaIcon(FontAwesomeIcons.floppyDisk),
                title: l10n.transcribeLaterTitle,
                subtitle: batchStorageFull ? l10n.transcribeLaterStorageFull : l10n.transcribeLaterDescription,
                value: _prefs.batchModeEnabled,
                onChanged: _setTranscribeLater,
              ),
            ],
          ),
          const SizedBox(height: OmiSpacing.xl),

          // Account
          OmiSettingsGroup(
            children: [
              OmiSettingsRow(
                leading: const FaIcon(FontAwesomeIcons.solidClipboard),
                title: l10n.userId,
                value: truncatedUid,
                showChevron: false,
                onTap: () => OmiClipboard.copy(context, uid, what: l10n.userId),
              ),
              OmiSettingsRow(
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
