import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/open_loops.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/pages/review/widgets/review_parts.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// One open-loop card from "Questions for you": the question and context line
/// the card writer rendered, shown verbatim, plus the only three answers a
/// card accepts. Unlike review questions there is no detail sheet — a card is
/// self-contained by contract, and the evidence behind it stays server-side.
class OpenLoopQuestionCard extends StatelessWidget {
  const OpenLoopQuestionCard({super.key, required this.card, this.margin = EdgeInsets.zero});

  final OpenLoopCard card;
  final EdgeInsetsGeometry margin;

  @override
  Widget build(BuildContext context) {
    final contextLine = card.contextLine;
    return Container(
      key: ValueKey('open_loop_card_${card.cardId}'),
      margin: margin,
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.md, OmiSpacing.md, OmiSpacing.sm),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  width: 40,
                  height: 40,
                  decoration: BoxDecoration(color: OmiColors.surface2, shape: BoxShape.circle),
                  child: Icon(Icons.help_outline, size: 20, color: OmiColors.textPrimary),
                ),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(
                  child: Semantics(
                    label: [card.question, if (contextLine.isNotEmpty) contextLine].join('\n'),
                    excludeSemantics: true,
                    child: Padding(
                      padding: const EdgeInsets.only(top: OmiSpacing.xxs),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          // Self-contained by contract: never truncated, wraps when long.
                          Text(card.question, style: OmiType.headline),
                          if (contextLine.isNotEmpty) ...[
                            const SizedBox(height: 3),
                            Text(
                              contextLine,
                              key: const Key('open_loop_context_line'),
                              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.md),
            child: Wrap(spacing: OmiSpacing.xs, runSpacing: OmiSpacing.xs, children: _answers(context)),
          ),
        ],
      ),
    );
  }

  List<Widget> _answers(BuildContext context) {
    final l10n = context.l10n;
    void give(OpenLoopAction action) => answerOpenLoopCard(context, card, action);
    return [
      ReviewAnswerPill(
        key: ValueKey('open_loop_done_${card.cardId}'),
        label: l10n.openLoopAnswerDone,
        primary: true,
        onPressed: () => give(OpenLoopAction.done),
      ),
      ReviewAnswerPill(
        key: ValueKey('open_loop_remind_${card.cardId}'),
        label: l10n.openLoopAnswerRemind,
        onPressed: () => give(OpenLoopAction.remind),
      ),
      ReviewAnswerPill(
        key: ValueKey('open_loop_drop_${card.cardId}'),
        label: l10n.openLoopAnswerDrop,
        onPressed: () => give(OpenLoopAction.drop),
      ),
    ];
  }
}

/// Sends [action] for [card] through the shared provider; says so if it did not
/// save. The message follows this request's outcome, per card: a 409 means the
/// card was answered elsewhere, anything else is a failed send.
Future<bool> answerOpenLoopCard(BuildContext context, OpenLoopCard card, OpenLoopAction action) async {
  final provider = context.read<ReviewProvider>();
  // A sheet may close before the answer settles; the root navigator outlives it.
  final host = Navigator.of(context, rootNavigator: true).context;
  final failedMessage = context.l10n.reviewAnswerFailed;
  final conflictMessage = context.l10n.reviewQuestionOutOfDate;
  OmiHaptics.light();
  final outcome = await provider.answerOpenLoop(card, action);
  if (outcome != OpenLoopAnswerStatus.saved) {
    OmiHaptics.error();
    final target = context.mounted ? context : host;
    if (target.mounted) {
      OmiFeedback.error(target, outcome == OpenLoopAnswerStatus.conflict ? conflictMessage : failedMessage);
    }
  }
  return outcome == OpenLoopAnswerStatus.saved;
}
