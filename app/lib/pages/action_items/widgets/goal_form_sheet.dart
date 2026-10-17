import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/goals.dart';
import 'package:omi/mobile/native_ui/ios_native_edit.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/providers/goals_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// What the goal sheet saves.
typedef GoalSaveCallback = FutureOr<void> Function(String title, double current, double target, String? emoji);

/// Opens the one goal sheet (Home and the Tasks page share it): a new goal, or [goal] for editing.
/// Cancel and Save are explicit, unsaved edits are guarded, and Delete (edit mode) is immediate
/// with Undo through [onDelete]. With the SwiftUI preview the sheet is a native form over the same
/// controllers, validation and callbacks.
Future<void> showGoalFormSheet(
  BuildContext context, {
  Goal? goal,
  required GoalSaveCallback onSave,
  VoidCallback? onDelete,
  List<String> emojiChoices = const [],
  String? initialEmoji,
}) {
  return showOmiEditSheet<void>(
    context: context,
    builder: (_) => GoalFormSheet(
      goal: goal,
      onSave: onSave,
      onDelete: onDelete,
      emojiChoices: emojiChoices,
      initialEmoji: initialEmoji,
    ),
  );
}

/// Deletes [goal] at once and offers Undo (docs/ux-contract.md §4, D5): no confirmation dialog.
/// [onDeleted] runs once the delete has committed on the server.
Future<void> deleteGoalWithUndo(
  BuildContext context,
  GoalsProvider provider,
  Goal goal, {
  VoidCallback? onDeleted,
}) async {
  OmiHaptics.medium();
  provider.stageDeleteGoal(goal.id);
  final undone = await OmiFeedback.undo(
    context,
    context.l10n.goalDeleted,
    onUndo: () => provider.undoStagedGoalDelete(goal.id),
  );
  if (undone) return;
  final deleted = await provider.commitStagedGoalDelete(goal.id);
  if (deleted) onDeleted?.call();
}

class GoalFormSheet extends StatefulWidget {
  const GoalFormSheet({
    super.key,
    this.goal,
    required this.onSave,
    this.onDelete,
    this.emojiChoices = const [],
    this.initialEmoji,
  });

  /// Null creates a goal.
  final Goal? goal;
  final GoalSaveCallback onSave;

  /// Shown as a trailing delete control in edit mode. Called after the sheet closes.
  final VoidCallback? onDelete;

  /// When not empty (and editing), an icon row lets the reader pick one.
  final List<String> emojiChoices;
  final String? initialEmoji;

  @override
  State<GoalFormSheet> createState() => _GoalFormSheetState();
}

class _GoalFormSheetState extends State<GoalFormSheet> {
  late final TextEditingController _titleController;
  late final TextEditingController _currentController;
  late final TextEditingController _targetController;
  late final String _initialTitle;
  late final String _initialCurrent;
  late final String _initialTarget;
  String? _emoji;

  /// Read only with the preview on: unsupported systems keep the classic sheet and its own guard.
  late final Future<bool> _native = supportsNativePresentation();

  bool get _isEditing => widget.goal != null;

  static String _rawNum(double v) => v == v.roundToDouble() ? v.toStringAsFixed(0) : v.toStringAsFixed(1);

  @override
  void initState() {
    super.initState();
    final goal = widget.goal;
    _initialTitle = goal?.title ?? '';
    _initialCurrent = goal == null ? '0' : _rawNum(goal.currentValue);
    _initialTarget = goal == null ? '100' : _rawNum(goal.targetValue);
    _titleController = TextEditingController(text: _initialTitle);
    _currentController = TextEditingController(text: _initialCurrent);
    _targetController = TextEditingController(text: _initialTarget);
    _emoji = widget.initialEmoji;
  }

  @override
  void dispose() {
    _titleController.dispose();
    _currentController.dispose();
    _targetController.dispose();
    super.dispose();
  }

  bool get _isDirty =>
      _titleController.text.trim() != _initialTitle.trim() ||
      _currentController.text.trim() != _initialCurrent ||
      _targetController.text.trim() != _initialTarget ||
      _emoji != widget.initialEmoji;

  void _save() {
    final title = _titleController.text.trim();
    if (title.isEmpty) return;
    final current = double.tryParse(_currentController.text) ?? widget.goal?.currentValue ?? 0;
    final target = double.tryParse(_targetController.text) ?? widget.goal?.targetValue ?? 100;
    Navigator.pop(context);
    widget.onSave(title, current, target, _emoji);
  }

  void _delete() {
    Navigator.pop(context);
    widget.onDelete?.call();
  }

  Widget _field(String label, TextEditingController controller, {bool number = false, bool autofocus = false}) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(label, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
        const SizedBox(height: OmiSpacing.xs),
        TextField(
          controller: controller,
          autofocus: autofocus,
          keyboardType: number ? const TextInputType.numberWithOptions(decimal: true) : TextInputType.text,
          onChanged: (_) => setState(() {}),
          style: OmiType.callout,
          cursorColor: OmiColors.accent,
          decoration: InputDecoration(
            filled: true,
            fillColor: OmiColors.surface2,
            contentPadding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: 14),
            border: const OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide.none),
          ),
        ),
      ],
    );
  }

  void _setText(TextEditingController controller, Object? value) => setState(() => controller.text = value as String);

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final classic = OmiEditSheet(
      title: _isEditing ? l10n.editGoal : l10n.addGoal,
      isDirty: _isDirty,
      actions: [
        if (_isEditing && widget.onDelete != null)
          OmiIconButton(
            icon: const Icon(Icons.delete_outline),
            label: l10n.deleteGoal,
            isDestructive: true,
            onPressed: _delete,
          ),
      ],
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (_isEditing && widget.emojiChoices.isNotEmpty) ...[
              Text(l10n.icon, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
              const SizedBox(height: OmiSpacing.xs),
              SizedBox(
                height: kOmiMinTapTarget,
                child: ListView.separated(
                  scrollDirection: Axis.horizontal,
                  itemCount: widget.emojiChoices.length,
                  separatorBuilder: (_, __) => const SizedBox(width: OmiSpacing.xs),
                  itemBuilder: (context, index) {
                    final emoji = widget.emojiChoices[index];
                    final selected = emoji == _emoji;
                    return Semantics(
                      button: true,
                      selected: selected,
                      label: emoji,
                      child: GestureDetector(
                        onTap: () {
                          OmiHaptics.selection();
                          setState(() => _emoji = emoji);
                        },
                        child: Container(
                          width: kOmiMinTapTarget,
                          height: kOmiMinTapTarget,
                          decoration: BoxDecoration(
                            color: selected ? OmiColors.surface3 : OmiColors.surface2,
                            borderRadius: OmiRadius.mdAll,
                            border: selected ? Border.all(color: OmiColors.textSecondary, width: 2) : null,
                          ),
                          alignment: Alignment.center,
                          child: ExcludeSemantics(child: Text(emoji, style: OmiType.title3)),
                        ),
                      ),
                    );
                  },
                ),
              ),
              const SizedBox(height: OmiSpacing.md),
            ],
            _field(l10n.goalTitle, _titleController, autofocus: true),
            const SizedBox(height: OmiSpacing.md),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(child: _field(l10n.current, _currentController, number: true)),
                const SizedBox(width: OmiSpacing.md),
                Expanded(child: _field(l10n.target, _targetController, number: true)),
              ],
            ),
            const SizedBox(height: OmiSpacing.xl),
            Row(
              children: [
                Expanded(
                  child: OmiButton.secondary(label: l10n.cancel, expand: true, onPressed: () => Navigator.pop(context)),
                ),
                const SizedBox(width: OmiSpacing.sm),
                Expanded(
                  child: OmiButton(
                    key: const Key('goal_save_button'),
                    label: _isEditing ? l10n.save : l10n.addGoal,
                    expand: true,
                    onPressed: _titleController.text.trim().isEmpty ? null : _save,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
    if (!nativePresentationEnabled) return classic;
    return FutureBuilder<bool>(
      future: _native,
      builder: (context, support) => support.data == true ? _nativeForm(classic) : classic,
    );
  }

  Widget _nativeForm(Widget classic) {
    final l10n = context.l10n;
    final emoji = _emoji;
    return IosNativeEdit(
      title: _isEditing ? l10n.editGoal : l10n.addGoal,
      isDirty: _isDirty,
      fallback: classic,
      sections: [
        NativeSection('goal_editor', [
          if (_isEditing && widget.emojiChoices.isNotEmpty && emoji != null && emoji.isNotEmpty)
            NativeRow(
              'goal_emoji',
              l10n.icon,
              kind: 'choice',
              value: emoji,
              // A goal may carry a keyword emoji the picker does not list; it stays selectable.
              options: {
                if (!widget.emojiChoices.contains(emoji)) emoji: emoji,
                for (final choice in widget.emojiChoices) choice: choice,
              },
              action: (value) {
                OmiHaptics.selection();
                setState(() => _emoji = value as String);
              },
            ),
          NativeRow('goal_title', l10n.goalTitle,
              kind: 'text', value: _titleController.text, action: (value) => _setText(_titleController, value)),
          NativeRow('goal_current', l10n.current,
              kind: 'text',
              keyboard: 'decimal',
              value: _currentController.text,
              action: (value) => _setText(_currentController, value)),
          NativeRow('goal_target', l10n.target,
              kind: 'text',
              keyboard: 'decimal',
              value: _targetController.text,
              action: (value) => _setText(_targetController, value)),
          if (_isEditing && widget.onDelete != null)
            NativeRow('goal_delete', l10n.deleteGoal, destructive: true, action: (_) => _delete()),
        ]),
      ],
      toolbar: [
        NativeRow('goal_save', _isEditing ? l10n.save : l10n.addGoal,
            enabled: _titleController.text.trim().isNotEmpty, action: (_) => _save()),
      ],
    );
  }
}
