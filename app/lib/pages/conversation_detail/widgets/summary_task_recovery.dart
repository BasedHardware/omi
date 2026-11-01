import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/providers/task_suggestions_controller.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// An explicit reader gesture recovers older desktop summaries after suggestions expire.
/// Phone extraction keeps its existing automatic delivery; it must not get a second writer.
class SummaryTaskRecovery extends StatelessWidget {
  const SummaryTaskRecovery({super.key, required this.conversation});

  final ServerConversation conversation;

  @override
  Widget build(BuildContext context) {
    final state = context.watch<ActionItemsProvider?>()?.suggestions;
    if (state == null ||
        conversation.source != ConversationSource.desktop ||
        conversation.status != ConversationStatus.completed ||
        conversation.discarded ||
        conversation.isLocked ||
        !conversation.structured.actionItems
            .any((item) => !item.completed && !item.deleted && item.description.trim().isNotEmpty)) {
      return const SizedBox.shrink();
    }
    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: OmiButton.secondary(
        key: const ValueKey('summary_add_tasks'),
        label: context.l10n.reviewAddTask,
        icon: Icons.playlist_add_rounded,
        onPressed: () {
          showOmiSheet<void>(
            context: context,
            title: context.l10n.actionItems,
            builder: (_) => _SummaryTaskPicker(conversation: conversation, controller: state),
          );
        },
      ),
    );
  }
}

class _SummaryTaskPicker extends StatelessWidget {
  const _SummaryTaskPicker({required this.conversation, required this.controller});

  final ServerConversation conversation;
  final TaskSuggestionsController controller;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: controller,
      builder: (context, _) => SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            for (final entry in conversation.structured.actionItems.indexed)
              if (!entry.$2.completed && !entry.$2.deleted && entry.$2.description.trim().isNotEmpty)
                Padding(
                  padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      Text(entry.$2.description, style: OmiType.callout),
                      if (controller.summarySaved(
                          conversation.id, entry.$2.sourceIndex ?? entry.$1, entry.$2.description))
                        Semantics(
                          liveRegion: true,
                          child: Text(context.l10n.sharedTasksAdded(1), style: OmiType.footnote),
                        )
                      else
                        Align(
                          alignment: AlignmentDirectional.centerStart,
                          child: OmiButton.secondary(
                            key: ValueKey('summary_add_task_${entry.$2.sourceIndex ?? entry.$1}'),
                            label: context.l10n.reviewAddTask,
                            size: OmiButtonSize.compact,
                            onPressed: () async {
                              final saved = await controller.addSummaryTask(
                                conversation.id,
                                entry.$2.sourceIndex ?? entry.$1,
                                entry.$2.description,
                              );
                              if (!saved && context.mounted) {
                                OmiFeedback.error(context, context.l10n.reviewAnswerFailed);
                              }
                            },
                          ),
                        ),
                      Divider(color: OmiColors.border),
                    ],
                  ),
                ),
          ],
        ),
      ),
    );
  }
}
