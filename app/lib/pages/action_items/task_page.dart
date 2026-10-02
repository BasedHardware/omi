import 'dart:async';

import 'package:collection/collection.dart';
import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/schema/schema.dart';
import 'package:omi/pages/action_items/task_delete_undo.dart';
import 'package:omi/pages/action_items/task_export.dart';
import 'package:omi/pages/action_items/widgets/action_item_form_sheet.dart' show DateTimePickerSheet;
import 'package:omi/pages/action_items/widgets/task_row_parts.dart';
import 'package:omi/pages/chat/widgets/content_blocks/conversation_link_blocks.dart' show openChatBlockConversation;
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/action_items_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Opens [item] on its own page (the task's text as the title, then due date, completion and the
/// actions). New tasks still use the sheet: [showActionItemFormSheet].
///
/// A paywalled task can't be read in full or changed (the backend answers 402 to every edit), so
/// it goes to the plan page instead, like a locked conversation.
Future<void> openTaskPage(BuildContext context, ActionItemWithMetadata item) {
  if (item.isLocked) return routeToPage(context, const UsagePage(showUpgradeDialog: true));
  return routeToPage(context, TaskPage(item: item));
}

/// One task, full screen: the conversation page's chrome (a back button, a Save pill that wakes up
/// when something changed), the text as a large editable title, a line back to the conversation it was
/// heard in, then Due (with the quick chips) and Mark Complete in one card and Export / Delete in another.
///
/// Text and due date save on Save; completion saves the moment it is tapped, like the list's ring.
/// Leaving with unsaved edits asks first (docs/ux-contract.md §2). Delete is immediate with Undo.
class TaskPage extends StatefulWidget {
  const TaskPage({super.key, required this.item});

  final ActionItemWithMetadata item;

  @override
  State<TaskPage> createState() => _TaskPageState();
}

class _TaskPageState extends State<TaskPage> {
  late final TextEditingController _text = TextEditingController(text: widget.item.description);
  late DateTime? _dueDate = widget.item.dueAt;
  late bool _completed = widget.item.completed;
  bool _saving = false;
  bool _saveFailed = false;
  bool _asking = false;
  bool _toggling = false;

  @override
  void dispose() {
    _text.dispose();
    super.dispose();
  }

  /// Unsaved text or date. Completion is not part of it: it saves the moment it is tapped.
  bool get _isDirty => _text.text.trim() != widget.item.description.trim() || _dueDate != widget.item.dueAt;

  Future<void> _save() async {
    if (_saving || _text.text.trim().isEmpty) return;
    final provider = context.read<ActionItemsProvider>();
    final hostContext = Navigator.of(context).context;
    final l10n = context.l10n;
    final item = widget.item;
    final description = _text.text.trim();
    final descriptionChanged = description != item.description;
    final dateChanged = _dueDate != item.dueAt;
    setState(() {
      _saving = true;
      _saveFailed = false;
    });
    var saved = true;
    try {
      if (descriptionChanged) saved = await provider.updateActionItemDescription(item, description) && saved;
      if (dateChanged) saved = await provider.updateActionItemDueDate(item, _dueDate) && saved;
      if (saved && (descriptionChanged || dateChanged)) {
        PlatformManager.instance.analytics.actionItemEdited(
          actionItemId: item.id,
          titleChanged: descriptionChanged,
          dateChanged: dateChanged,
        );
      }
    } catch (_) {
      saved = false;
    }
    if (!mounted) return;
    setState(() {
      _saving = false;
      _saveFailed = !saved;
    });
    if (!saved) return;
    OmiHaptics.light();
    Navigator.pop(context);
    if (hostContext.mounted) OmiFeedback.confirm(hostContext, l10n.actionItemUpdated);
  }

  Future<void> _close() async {
    if (_saving) return;
    if (!_isDirty) {
      Navigator.pop(context);
      return;
    }
    if (_asking) return;
    _asking = true;
    final discard = await confirmDiscardChanges(context);
    _asking = false;
    if (discard && mounted) Navigator.pop(context);
  }

  /// Completion is instant everywhere (the list, Home, here): no Save needed.
  Future<void> _toggleCompleted() async {
    if (_toggling) return;
    final next = !_completed;
    OmiHaptics.light();
    // The row is disabled until the server answers, so two taps cannot race each other.
    setState(() {
      _completed = next;
      _toggling = true;
    });
    final provider = context.read<ActionItemsProvider>();
    final ok = await provider.updateActionItemState(widget.item, next);
    if (!mounted) return;
    // Another surface may have toggled the same task meanwhile; the provider's record, not this
    // request's outcome, says where the task stands now.
    final latest = provider.actionItems.firstWhereOrNull((i) => i.id == widget.item.id);
    setState(() {
      _toggling = false;
      _completed = latest?.completed ?? (ok ? next : !next);
    });
    if (!ok) {
      OmiFeedback.error(context, context.l10n.failedToUpdateActionItem);
    } else if (next) {
      PlatformManager.instance.analytics.actionItemCompleted(fromTab: 'Task Page');
    }
  }

  Future<void> _openConversation() async {
    final id = widget.item.conversationId;
    if (id == null) return;
    OmiHaptics.selection();
    final opened = await openChatBlockConversation(context, conversationId: id);
    if (!opened && mounted) OmiFeedback.info(context, context.l10n.conversationNotFoundOrDeleted);
  }

  Future<void> _pickDueDate() async {
    final result = await showOmiSurfaceSheet<DateTime>(
      context: context,
      builder: (context) => DateTimePickerSheet(initialDateTime: _dueDate, minimumDate: widget.item.createdAt),
    );
    if (result != null && mounted) setState(() => _dueDate = result);
  }

  void _selectQuickDate(int days) {
    final now = DateTime.now();
    final date = DateTime(now.year, now.month, now.day + days, 18);
    OmiHaptics.selection();
    setState(() => _dueDate = date.isBefore(now) ? DateTime(now.year, now.month, now.day, 23, 59, 59) : date);
  }

  String _formatDueDate(DateTime date) {
    final dates = OmiDateFormat.of(context);
    final now = DateTime.now();
    final tomorrow = DateTime(now.year, now.month, now.day + 1);
    final day = DateTime(date.year, date.month, date.day) == tomorrow ? context.l10n.tomorrow : dates.dayHeader(date);
    return '$day · ${dates.time(date)}';
  }

  void _delete() {
    final provider = context.read<ActionItemsProvider>();
    unawaited(deleteTaskWithUndo(context, provider, widget.item));
    Navigator.pop(context);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final item = widget.item;
    final canSave = _isDirty && !_saving && _text.text.trim().isNotEmpty;
    return PopScope<Object?>(
      canPop: !_isDirty,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _close();
      },
      child: Scaffold(
        backgroundColor: OmiColors.surface0,
        body: SafeArea(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(10, 6, 16, 0),
                child: Row(
                  children: [
                    OmiBackButton.circled(onPressed: _close),
                    const Spacer(),
                    OmiButton(
                      key: const Key('task_save_button'),
                      label: _saveFailed ? l10n.tryAgain : l10n.save,
                      size: OmiButtonSize.compact,
                      isLoading: _saving,
                      onPressed: canSave ? _save : null,
                    ),
                  ],
                ),
              ),
              Expanded(
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(16, 8, 16, 32),
                  children: [
                    TextField(
                      key: const Key('task_description'),
                      controller: _text,
                      enabled: !_saving,
                      onChanged: (_) => setState(() {}),
                      maxLines: null,
                      minLines: 1,
                      maxLength: 4096,
                      textInputAction: TextInputAction.done,
                      style: OmiType.title1.copyWith(
                        letterSpacing: -0.6,
                        height: 1.2,
                        color: _completed ? OmiColors.textTertiary : OmiColors.textPrimary,
                        decoration: _completed ? TextDecoration.lineThrough : null,
                        decorationColor: OmiColors.border,
                      ),
                      cursorColor: OmiColors.accent,
                      decoration: const InputDecoration(
                        counterText: '',
                        border: InputBorder.none,
                        contentPadding: EdgeInsets.zero,
                        isDense: true,
                      ),
                      onSubmitted: (_) => FocusScope.of(context).unfocus(),
                    ),
                    if (item.conversationId != null) ...[
                      const SizedBox(height: 10),
                      _SourceLine(onTap: _openConversation),
                    ],
                    const SizedBox(height: 24),
                    _Card(
                      children: [
                        // The date is the row's text ("Tomorrow · 9:00 AM"), or "Add Due Date" when there is none.
                        _CardRow(
                          leading: const Icon(Icons.schedule_outlined, size: 22),
                          title: _dueDate != null ? _formatDueDate(_dueDate!) : l10n.addDueDate,
                          onTap: _saving ? null : _pickDueDate,
                          trailing: _dueDate == null
                              ? null
                              : OmiIconButton(
                                  icon: const Icon(Icons.close, size: 18),
                                  label: l10n.clearDueDate,
                                  color: OmiColors.textSecondary,
                                  onPressed: _saving ? null : () => setState(() => _dueDate = null),
                                ),
                        ),
                        Padding(
                          padding: const EdgeInsets.fromLTRB(54, 0, 16, 12),
                          child: Wrap(
                            spacing: OmiSpacing.xs,
                            children: [
                              for (final days in [0, 1, 7])
                                ActionChip(
                                  key: ValueKey('task_quick_date_$days'),
                                  label: Text(days == 0
                                      ? l10n.today
                                      : days == 1
                                          ? l10n.tomorrow
                                          : l10n.nextWeek),
                                  onPressed: _saving ? null : () => _selectQuickDate(days),
                                  backgroundColor: OmiColors.surface2,
                                  labelStyle: OmiType.footnote,
                                  side: BorderSide(color: OmiColors.surface2),
                                ),
                            ],
                          ),
                        ),
                        _CardRow(
                          key: const Key('task_completed_toggle'),
                          leading: TaskCompletionMark(completed: _completed),
                          title: _completed ? l10n.completed : l10n.markComplete,
                          onTap: _toggling ? null : _toggleCompleted,
                          showChevron: false,
                          semanticsChecked: _completed,
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    _Card(
                      children: [
                        _CardRow(
                          leading: const Icon(Icons.ios_share_rounded, size: 22),
                          title: l10n.exportButton,
                          onTap: _saving ? null : () => exportTaskToConnectedApp(context, widget.item),
                          showChevron: false,
                        ),
                        _CardRow(
                          leading: const Icon(Icons.delete_outline, size: 22),
                          title: l10n.deleteActionItem,
                          onTap: _saving ? null : _delete,
                          showChevron: false,
                          isDestructive: true,
                        ),
                      ],
                    ),
                    if (_saveFailed) ...[
                      const SizedBox(height: 16),
                      Semantics(
                        liveRegion: true,
                        child: Text(l10n.failedToUpdateActionItem,
                            style: OmiType.footnote.copyWith(color: OmiColors.danger)),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// "Open conversation" under the title, for a task Omi heard: a waveform, the label, a chevron.
class _SourceLine extends StatelessWidget {
  const _SourceLine({required this.onTap});

  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: context.l10n.openConversation,
      onTap: onTap,
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        borderRadius: OmiRadius.smAll,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
          child: Row(
            children: [
              Icon(Icons.graphic_eq, size: 18, color: OmiColors.textTertiary),
              const SizedBox(width: 10),
              Expanded(
                child:
                    Text(context.l10n.openConversation, style: OmiType.callout.copyWith(color: OmiColors.textTertiary)),
              ),
              Icon(Icons.chevron_right_rounded, size: 20, color: OmiColors.textTertiary),
            ],
          ),
        ),
      ),
    );
  }
}

/// A rounded [OmiColors.surface1] card of rows, a hairline between rows starting at the title.
class _Card extends StatelessWidget {
  const _Card({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: OmiColors.surface1,
      borderRadius: OmiRadius.lgAll,
      clipBehavior: Clip.antiAlias,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (var i = 0; i < children.length; i++) ...[
            if (i > 0 && children[i] is _CardRow)
              Padding(
                padding: const EdgeInsetsDirectional.only(start: 54),
                child: Container(height: 0.5, color: OmiColors.border),
              ),
            children[i],
          ],
        ],
      ),
    );
  }
}

class _CardRow extends StatelessWidget {
  const _CardRow({
    super.key,
    required this.leading,
    required this.title,
    required this.onTap,
    this.trailing,
    this.showChevron = true,
    this.isDestructive = false,
    this.semanticsChecked,
  });

  final Widget leading;
  final String title;
  final Widget? trailing;
  final VoidCallback? onTap;
  final bool showChevron;
  final bool isDestructive;
  final bool? semanticsChecked;

  @override
  Widget build(BuildContext context) {
    final color = isDestructive ? OmiColors.danger : OmiColors.textPrimary;
    // The row is one control for assistive tech; a trailing control (the due-date ×) stays its
    // own, outside the merged subtree, so it is still announced and tappable.
    final row = Semantics(
      button: true,
      checked: semanticsChecked,
      label: title,
      onTap: onTap,
      excludeSemantics: true,
      child: InkWell(
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 52),
          child: Padding(
            padding: EdgeInsetsDirectional.only(start: 16, end: trailing != null ? 0 : 12),
            child: Row(
              children: [
                SizedBox(width: 22, child: Center(child: IconTheme(data: IconThemeData(color: color), child: leading))),
                const SizedBox(width: 16),
                Expanded(child: Text(title, style: OmiType.body.copyWith(color: color, letterSpacing: -0.4))),
                if (trailing == null && showChevron && onTap != null)
                  Padding(
                    padding: const EdgeInsetsDirectional.only(start: 2),
                    child: Icon(Icons.chevron_right_rounded, size: 20, color: OmiColors.textTertiary),
                  )
                else if (trailing == null)
                  const SizedBox(width: 4),
              ],
            ),
          ),
        ),
      ),
    );
    if (trailing == null) return row;
    return Row(
      children: [
        Expanded(child: row),
        Padding(padding: const EdgeInsetsDirectional.only(end: 8), child: trailing!),
      ],
    );
  }
}
