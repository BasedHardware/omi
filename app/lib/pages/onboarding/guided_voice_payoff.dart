import 'package:flutter/material.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'guided_voice_controller.dart';

class GuidedVoicePayoff extends StatelessWidget {
  const GuidedVoicePayoff({super.key, required this.flow});
  final GuidedVoiceController flow;

  @override
  Widget build(BuildContext context) => Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(context.l10n.guidedVoiceExperience('title'), style: OmiType.title1, key: const Key('payoff_title')),
          const SizedBox(height: OmiSpacing.lg),
          for (final answer in flow.savedAnswers) ...[
            DecoratedBox(
              decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
              child: Padding(
                padding: const EdgeInsets.all(OmiSpacing.md),
                child: Text(answer.text, style: OmiType.body),
              ),
            ),
            const SizedBox(height: OmiSpacing.sm),
          ],
          const SizedBox(height: OmiSpacing.lg),
          Text(context.l10n.guidedVoiceExperience('question'), style: OmiType.title3),
          const SizedBox(height: OmiSpacing.sm),
          if (flow.payoffLoading) ...[
            Text(context.l10n.guidedVoiceExperience('thinking'), style: OmiType.footnote),
            const SizedBox(height: OmiSpacing.sm),
          ],
          if (flow.payoffSource == 'fallback') ...[
            Text(context.l10n.guidedVoiceExperience('fallback'), style: OmiType.footnote),
            const SizedBox(height: OmiSpacing.sm),
          ],
          Semantics(
              liveRegion: true, child: Text(flow.payoffAnswer, key: const Key('payoff_answer'), style: OmiType.body)),
        ],
      );
}
