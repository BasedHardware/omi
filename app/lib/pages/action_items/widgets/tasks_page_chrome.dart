import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The To do tab's large title and open count (v2 `Tasks`, Rev 3 "To do").
class TasksPageTitle extends StatelessWidget {
  const TasksPageTitle({super.key, required this.openCount});

  final int openCount;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(OmiSize.screenMargin, OmiSpacing.xs, OmiSize.screenMargin, 0),
          child: Semantics(
            header: true,
            // Rev 3: the tab and its page are "To do".
            child: Text(context.l10n.toDo, style: OmiType.largeTitle, maxLines: 1, overflow: TextOverflow.ellipsis),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(OmiSize.screenMargin, 2, OmiSize.screenMargin, OmiSpacing.sm),
          child: Text(
            context.l10n.tasksCountLabel(openCount),
            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
          ),
        ),
      ],
    );
  }
}

/// The v2 quick add: a glass capsule above the tab bar that opens the new-task sheet.
class TasksQuickAdd extends StatelessWidget {
  const TasksQuickAdd({super.key, required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    void open() {
      OmiHaptics.light();
      onTap();
    }

    return Semantics(
      button: true,
      label: context.l10n.newTask,
      excludeSemantics: true,
      onTap: open,
      child: GestureDetector(
        key: const Key('action_items_quick_add'),
        behavior: HitTestBehavior.opaque,
        onTap: open,
        child: OmiGlass(
          borderRadius: OmiRadius.pillAll,
          child: SizedBox(
            height: OmiSize.primaryButton,
            child: Row(
              children: [
                const SizedBox(width: OmiSpacing.md),
                Icon(Icons.add_rounded, size: 22, color: OmiColors.textSecondary),
                const SizedBox(width: OmiSpacing.xs),
                Expanded(
                  child: Text(
                    context.l10n.newTask,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: OmiType.body.copyWith(color: OmiColors.textSecondary),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
