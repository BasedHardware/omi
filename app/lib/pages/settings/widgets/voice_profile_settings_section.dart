import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/providers/speaker_tag_prompts_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

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
          ],
        );
      },
    );
  }
}
