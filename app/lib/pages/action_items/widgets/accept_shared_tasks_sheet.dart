import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/action_items.dart' as action_items_api;
import 'package:omi/pages/action_items/widgets/task_row_parts.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';

class AcceptSharedTasksSheet extends StatefulWidget {
  final String token;
  final String senderName;
  final List<Map<String, dynamic>> tasks;
  final VoidCallback? onAccepted;

  const AcceptSharedTasksSheet({
    super.key,
    required this.token,
    required this.senderName,
    required this.tasks,
    this.onAccepted,
  });

  @override
  State<AcceptSharedTasksSheet> createState() => _AcceptSharedTasksSheetState();
}

class _AcceptSharedTasksSheetState extends State<AcceptSharedTasksSheet> {
  bool _isAccepting = false;

  Future<void> _acceptTasks() async {
    setState(() => _isAccepting = true);
    final l10n = context.l10n;

    final result = await action_items_api.acceptSharedActionItems(widget.token);

    if (!mounted) return;

    if (result != null) {
      final count = (result['count'] as num?)?.toInt() ?? 0;
      OmiHaptics.success();
      Navigator.pop(context);
      AppSnackbar.showSnackbar(l10n.sharedTasksAdded(count));
      widget.onAccepted?.call();
    } else {
      setState(() => _isAccepting = false);
      AppSnackbar.showSnackbarError(l10n.sharedTasksAcceptFailed);
    }
  }

  String _formatDueDate(String dateStr) {
    final date = DateTime.tryParse(dateStr);
    if (date == null) return dateStr;
    return OmiDateFormat.of(context).date(date.toLocal());
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    // Paints its own surface so it also works under a transparent showModalBottomSheet; the shell
    // (title, close X, insets) is the shared one.
    return ConstrainedBox(
      constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.7),
      child: Material(
        color: OmiColors.surface1,
        shape: const RoundedRectangleBorder(borderRadius: OmiRadius.sheetTop),
        clipBehavior: Clip.antiAlias,
        child: Padding(
          padding: const EdgeInsets.only(top: OmiSpacing.sm),
          child: OmiSheetScaffold(
            title: l10n.sharedTasksTitle(widget.senderName, widget.tasks.length),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Text(l10n.addToYourTaskList, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
                const SizedBox(height: OmiSpacing.md),
                Flexible(
                  child: ListView.builder(
                    shrinkWrap: true,
                    itemCount: widget.tasks.length,
                    itemBuilder: (context, index) {
                      final task = widget.tasks[index];
                      final description = task['description'] as String? ?? '';
                      final dueAt = task['due_at'] as String?;

                      return Container(
                        margin: const EdgeInsets.only(bottom: OmiSpacing.xs),
                        padding: const EdgeInsets.symmetric(horizontal: 14, vertical: OmiSpacing.sm),
                        decoration: BoxDecoration(
                          color: OmiColors.surface2,
                          borderRadius: OmiRadius.mdAll,
                          border: Border.all(color: OmiColors.border),
                        ),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Padding(
                              padding: EdgeInsets.only(top: 1),
                              child: TaskCompletionMark(completed: false, size: 20),
                            ),
                            const SizedBox(width: OmiSpacing.sm),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(description, style: OmiType.subhead),
                                  if (dueAt != null) ...[
                                    const SizedBox(height: OmiSpacing.xxs),
                                    Text(
                                      l10n.taskDueDate(_formatDueDate(dueAt)),
                                      style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                                    ),
                                  ],
                                ],
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
                ),
                const SizedBox(height: OmiSpacing.lg),
                OmiButton(
                  label: l10n.sharedTasksAddButton(widget.tasks.length),
                  expand: true,
                  isLoading: _isAccepting,
                  onPressed: _isAccepting ? null : _acceptTasks,
                ),
                const SizedBox(height: OmiSpacing.xs),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
