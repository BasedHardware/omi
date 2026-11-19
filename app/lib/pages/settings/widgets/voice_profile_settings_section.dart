import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/settings/widgets/ignored_voices_sheet.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The app-wide capture provider when one is reachable from this context, for
/// forwarding Settings-side voice restorations to a live capture. The provider
/// lives above the app shell, so in practice this only misses in isolated
/// widget tests — restoring then simply skips the capture-side retirement.
CaptureProvider? _liveCaptureProvider(BuildContext context) {
  try {
    return context.read<CaptureProvider>();
  } catch (_) {
    return null;
  }
}

/// Two switches that control voice learning: whether Omi asks the user to tag
/// voices, and whether naming someone saves a short voice sample of them.
class VoiceProfileSettingsSection extends StatefulWidget {
  const VoiceProfileSettingsSection({super.key});

  @override
  State<VoiceProfileSettingsSection> createState() => _VoiceProfileSettingsSectionState();
}

class _VoiceProfileSettingsSectionState extends State<VoiceProfileSettingsSection> {
  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      context.read<SpeakerTagPromptsProvider>().loadSettings();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<SpeakerTagPromptsProvider>(
      builder: (context, provider, _) {
        final enabled = provider.settingsLoaded;
        return OmiSettingsGroup(
          header: context.l10n.voiceRecognitionSettings,
          children: [
            OmiSettingsRow.toggle(
              key: const Key('voice_settings_ask_to_tag_switch'),
              title: context.l10n.voiceSettingsAskToTag,
              subtitle: context.l10n.voiceSettingsAskToTagSubtitle,
              value: provider.speakerTagPromptsEnabled,
              onChanged: enabled ? (value) => provider.setSpeakerTagPromptsEnabled(value) : null,
            ),
            OmiSettingsRow.toggle(
              key: const Key('voice_settings_save_others_switch'),
              title: context.l10n.speakerTagPromptSaveVoicesTitle,
              subtitle: context.l10n.voiceSettingsSaveOthersSubtitle,
              value: provider.saveOtherVoiceProfiles,
              onChanged: enabled ? (value) => provider.setSaveOtherVoiceProfiles(value, fromFirstPrompt: false) : null,
            ),
            OmiSettingsRow(
              key: const Key('voice_settings_ignored_voices'),
              title: context.l10n.ignoredVoicesTitle,
              subtitle: context.l10n.ignoredVoicesSubtitle,
              onTap: () {
                // A restoration while the same live capture stays active must
                // retire the capture-side exclusion too: the restore writes no
                // positive label, so no snapshot can ever satisfy the
                // manual-positive retirement condition. Pass the signal so the
                // voice becomes eligible for prompts again immediately.
                final capture = _liveCaptureProvider(context);
                showIgnoredVoicesSheet(
                  context,
                  onRestored: capture?.onIgnoredVoiceRestored,
                );
              },
            ),
          ],
        );
      },
    );
  }
}
