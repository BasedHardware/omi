import 'package:flutter/material.dart';

import 'package:omi/backend/schema/chat_content_block.dart';
import 'package:omi/utils/l10n_extensions.dart';

import 'chat_block_chrome.dart';

/// Renders a `questionCard` block: the question plus its prepared answers.
///
/// Tapping an option sends its `preparedAnswer` as a normal chat message — the
/// same path the initial suggestion chips already use — so the runtime stays
/// authoritative for what an answer means. A deferral option is not special:
/// it sends its own prepared answer. Once `selectedOptionId` is set the card
/// keeps the question readable and shows only the chosen option, disabled, so
/// no stale chip ever looks tappable.
class QuestionCardBlock extends StatelessWidget {
  const QuestionCardBlock({super.key, required this.block, required this.sendMessage});

  final QuestionCardContentBlock block;
  final void Function(String) sendMessage;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final colorScheme = Theme.of(context).colorScheme;
    final selectedId = block.selectedOptionId;
    final answered = selectedId != null;
    final options = answered
        ? block.options.where((option) => option.optionId == selectedId).toList(growable: false)
        : block.options;

    return ChatBlockCard(
      key: Key('chat-block-questionCard-${block.id}'),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          ChatBlockEyebrow(icon: Icons.help_outline, label: l10n.chatBlockQuestion),
          const SizedBox(height: 6),
          Text(block.text, style: Theme.of(context).textTheme.bodyMedium),
          if (options.isNotEmpty) ...[
            const SizedBox(height: 8),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                for (final option in options)
                  OutlinedButton(
                    key: Key('chat-block-questionCard-${block.id}-option-${option.optionId}'),
                    onPressed: answered ? null : () => sendMessage(option.preparedAnswer),
                    style: OutlinedButton.styleFrom(
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      minimumSize: const Size(0, 32),
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                      foregroundColor: colorScheme.onSurface,
                      side: BorderSide(color: colorScheme.outline.withValues(alpha: 0.55)),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                    ),
                    child: Text(option.label, style: Theme.of(context).textTheme.bodySmall),
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}
