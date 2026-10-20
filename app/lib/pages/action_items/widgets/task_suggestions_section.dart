import 'package:flutter/material.dart';

import 'package:omi/providers/task_suggestions_controller.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The same server-owned suggestions reviewed on desktop, reachable even with zero tasks.
class TaskSuggestionsSection extends StatelessWidget {
  const TaskSuggestionsSection({super.key, required this.controller});

  final TaskSuggestionsController? controller;

  @override
  Widget build(BuildContext context) {
    final state = controller;
    if (state == null) return const SizedBox.shrink();
    return ListenableBuilder(
      listenable: state,
      builder: (context, _) {
        if (state.items.isEmpty && state.loadProblem == null && !state.loading) return const SizedBox.shrink();
        final l10n = context.l10n;
        return Padding(
          key: const ValueKey('task_suggestions'),
          padding: const EdgeInsets.all(OmiSpacing.md),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              OmiSectionHeader(l10n.reviewTitle),
              if (state.loading) const LinearProgressIndicator(),
              if (state.loadProblem != null) ...[
                Text(l10n.reviewLoadFailed, style: OmiType.subhead),
                Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: OmiButton.secondary(label: l10n.tryAgain, onPressed: state.load),
                ),
              ],
              for (final item in state.items)
                Padding(
                  key: ValueKey('task_suggestion_${item.candidateId}'),
                  padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      if (item.workstreamProposal != null) ...[
                        Text(l10n.reviewProject, style: OmiType.footnote),
                        Text(item.workstreamProposal!.title, style: OmiType.headline),
                        Text(item.workstreamProposal!.objective, style: OmiType.subhead),
                        const SizedBox(height: OmiSpacing.sm),
                      ],
                      Text(TaskSuggestionsController.description(item), style: OmiType.callout),
                      if (state.saved(item.candidateId))
                        Semantics(liveRegion: true, child: Text(l10n.sharedTasksAdded(1), style: OmiType.footnote)),
                      Wrap(
                        spacing: OmiSpacing.sm,
                        children: [
                          OmiButton.secondary(
                            key: ValueKey('accept_task_${item.candidateId}'),
                            label: state.saved(item.candidateId) ? l10n.tryAgain : l10n.reviewAddTask,
                            size: OmiButtonSize.compact,
                            isLoading: state.busy(item.candidateId),
                            onPressed: state.busy(item.candidateId)
                                ? null
                                : () async {
                                    final ok = state.saved(item.candidateId)
                                        ? await state.retrySaved(item.candidateId)
                                        : await state.accept(item);
                                    if (!ok && context.mounted) {
                                      OmiFeedback.error(
                                          context,
                                          state.saved(item.candidateId)
                                              ? l10n.somethingWentWrong
                                              : l10n.reviewAnswerFailed);
                                    }
                                  },
                          ),
                          if (!state.saved(item.candidateId))
                            OmiButton.tertiary(
                              key: ValueKey('dismiss_task_${item.candidateId}'),
                              label: l10n.dismiss,
                              size: OmiButtonSize.compact,
                              onPressed: state.busy(item.candidateId)
                                  ? null
                                  : () async {
                                      final ok = await state.dismiss(item);
                                      if (!ok && context.mounted) OmiFeedback.error(context, l10n.reviewAnswerFailed);
                                    },
                            ),
                        ],
                      ),
                      Divider(color: OmiColors.border),
                    ],
                  ),
                ),
            ],
          ),
        );
      },
    );
  }
}
