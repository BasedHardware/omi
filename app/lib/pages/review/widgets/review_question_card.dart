import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/review.dart';
import 'package:omi/pages/review/review_item_sheet.dart';
import 'package:omi/pages/review/widgets/review_parts.dart';
import 'package:omi/providers/review_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// One question from the Review queue, the same everywhere it appears (Review, a transcript, a
/// person page): a leading control, the one-line question, a chevron, and one row of quick answers.
///
/// Tapping anything but a quick answer or the play button opens the detail sheet, which holds the
/// evidence and every answer.
class ReviewQuestionCard extends StatelessWidget {
  const ReviewQuestionCard({super.key, required this.item, this.margin = EdgeInsets.zero});

  final ReviewItem item;
  final EdgeInsetsGeometry margin;

  @override
  Widget build(BuildContext context) {
    final provider = context.watch<ReviewProvider>();
    final question = reviewQuestion(context, item);
    final quote = item.kind == ReviewItemKind.task ? null : item.quote;
    return Container(
      key: ValueKey('review_card_${item.itemId}'),
      margin: margin,
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.xlAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.md, OmiSpacing.xs, OmiSpacing.sm),
            child: Row(
              children: [
                if (item.kind == ReviewItemKind.speaker)
                  ReviewPlayButton(
                    playing: provider.playingItemId == item.itemId,
                    onPressed: () => provider.togglePlay(item),
                  )
                else
                  ReviewKindBadge(kind: item.kind),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(
                  child: Semantics(
                    button: true,
                    label: question,
                    hint: context.l10n.reviewOpenDetailsHint,
                    excludeSemantics: true,
                    child: InkWell(
                      key: ValueKey('review_card_open_${item.itemId}'),
                      borderRadius: OmiRadius.mdAll,
                      onTap: () => showReviewItemSheet(context, item),
                      child: ConstrainedBox(
                        constraints: const BoxConstraints(minHeight: 44),
                        child: Row(
                          children: [
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  Text(question, style: OmiType.headline, maxLines: 2, overflow: TextOverflow.ellipsis),
                                  if (quote != null) ...[
                                    const SizedBox(height: 3),
                                    Text(
                                      '“$quote”',
                                      maxLines: 1,
                                      overflow: TextOverflow.ellipsis,
                                      style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                                    ),
                                  ],
                                ],
                              ),
                            ),
                            Icon(Icons.chevron_right, color: OmiColors.textTertiary, size: 22),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.fromLTRB(OmiSpacing.md, 0, OmiSpacing.md, OmiSpacing.md),
            child: Wrap(spacing: OmiSpacing.xs, runSpacing: OmiSpacing.xs, children: _quickAnswers(context)),
          ),
        ],
      ),
    );
  }

  List<Widget> _quickAnswers(BuildContext context) {
    final l10n = context.l10n;
    void give(ReviewAnswer answer) => answerReviewItem(context, item, answer);
    void open() => showReviewItemSheet(context, item);
    switch (item.kind) {
      case ReviewItemKind.speaker:
        final candidates = item.speaker!.candidates.take(2);
        return [
          for (final person in candidates)
            ReviewAnswerPill(
                label: person.name, onPressed: () => give(ReviewAnswer.speaker(personId: person.personId))),
          if (candidates.isEmpty)
            ReviewAnswerPill(label: l10n.reviewAnswerMe, onPressed: () => give(const ReviewAnswer.speaker(isMe: true))),
          ReviewAnswerPill(
              key: ValueKey('review_other_${item.itemId}'), label: l10n.reviewAnswerOther, onPressed: open),
        ];
      case ReviewItemKind.task:
        return [
          ReviewAnswerPill(
              label: l10n.reviewAddTask, primary: true, onPressed: () => give(const ReviewAnswer.acceptTask())),
          ReviewAnswerPill(label: l10n.dismiss, onPressed: () => give(const ReviewAnswer.dismissTask())),
        ];
      case ReviewItemKind.samePerson:
        return [
          ReviewAnswerPill(label: l10n.yes, primary: true, onPressed: () => give(const ReviewAnswer.samePerson(true))),
          ReviewAnswerPill(label: l10n.no, onPressed: () => give(const ReviewAnswer.samePerson(false))),
        ];
      case ReviewItemKind.spelling:
        return [
          for (final option in item.spelling!.options.take(3))
            ReviewAnswerPill(label: option, onPressed: () => give(ReviewAnswer.spelling(option))),
        ];
    }
  }
}

/// Sends [answer] for [item] through the shared provider; says so if it did not save.
Future<bool> answerReviewItem(BuildContext context, ReviewItem item, ReviewAnswer answer) async {
  final provider = context.read<ReviewProvider>();
  final messenger = ScaffoldMessenger.maybeOf(context);
  final failedMessage = context.l10n.reviewAnswerFailed;
  OmiHaptics.light();
  final saved = await provider.answer(item, answer);
  if (!saved) {
    OmiHaptics.error();
    if (context.mounted) {
      OmiFeedback.error(context, failedMessage);
    } else {
      messenger?.showSnackBar(SnackBar(content: Text(failedMessage)));
    }
  }
  return saved;
}
