import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/action_items/widgets/task_row_parts.dart';
import 'package:omi/pages/settings/settings_destinations.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// A new account's first To do (IMG_1157): teach Omi your voice. It stands first among the tasks,
/// drawn like one, while the voice profile is missing; a tap opens the voice setup exactly as its
/// other entry points do, and the task leaves once the profile exists. (It used to be a card
/// squeezed above the Conversations search.)
class VoiceSetupTask extends StatelessWidget {
  const VoiceSetupTask({super.key});

  Future<void> _open(BuildContext context) async {
    OmiHaptics.selection();
    PlatformManager.instance.analytics.pageOpened('Speech Profile Memories');
    final before = SharedPreferencesUtil().hasSpeakerProfile;
    await openVoiceProfile(context);
    final after = SharedPreferencesUtil().hasSpeakerProfile;
    if (before == after || !context.mounted) return;
    await context.read<CaptureProvider>().onRecordProfileSettingChanged();
    if (!context.mounted) return;
    context.read<HomeProvider>().setSpeakerProfile(after);
  }

  @override
  Widget build(BuildContext context) {
    final show = context.select<HomeProvider?, bool>(
      (home) => home != null && !home.isLoading && !home.hasSpeakerProfile,
    );
    if (!show) return const SizedBox.shrink();
    final l10n = context.l10n;
    return Padding(
      key: const ValueKey('todo_voice_setup'),
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Semantics(
        button: true,
        label: '${l10n.teachOmiYourVoice}, ${l10n.voiceSetupTaskSubline}',
        excludeSemantics: true,
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => _open(context),
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: Row(
              children: [
                // The task's open ring, where a task's completion mark sits.
                const SizedBox(width: 44, height: 48, child: Center(child: TaskCompletionMark(completed: false))),
                Expanded(
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 12),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Text(l10n.teachOmiYourVoice, style: OmiType.body),
                        const SizedBox(height: 2),
                        OmiBalancedText(
                          l10n.voiceSetupTaskSubline,
                          style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: OmiSpacing.xs),
                OmiGlyph(OmiGlyphs.chevronRight, size: 14, color: OmiColors.textTertiary),
                const SizedBox(width: OmiSpacing.xs),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
