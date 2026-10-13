import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
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
          if (flow.payoffLoading) Text(context.l10n.guidedVoiceExperience('thinking'), style: OmiType.footnote),
          if (flow.payoffSource == 'chat') ...[
            Text(context.l10n.guidedVoiceExperience('question'), style: OmiType.title3),
            const SizedBox(height: OmiSpacing.sm),
            Semantics(
              key: const Key('payoff_answer'),
              liveRegion: true,
              child: MarkdownBody(data: flow.payoffAnswer, styleSheet: MarkdownStyleSheet(p: OmiType.body)),
            ),
          ] else if (!flow.payoffLoading)
            Text(context.l10n.guidedVoiceExperience('fallback'),
                key: const Key('payoff_fallback'), style: OmiType.body),
        ],
      );
}
