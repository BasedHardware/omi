import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'memory_delete_undo.dart';

/// Opens [memory]: the edit sheet when it can be edited, otherwise the same sheet read-only (full
/// text, nothing to save). Pass [readOnly] to open an editable memory for reading only (the
/// long-press menu's Open).
Future<void> showMemoryQuickEditSheet(
  BuildContext context,
  Memory memory,
  MemoriesProvider provider, {
  Function(BuildContext, Memory, MemoriesProvider)? onDelete,
  bool readOnly = false,
}) {
  return showOmiEditSheet<void>(
    context: context,
    builder: (context) => MemoryEditSheet(
      memory: memory,
      provider: provider,
      onDelete: onDelete,
      readOnly: readOnly || !memoryIsEditable(memory),
    ),
  );
}

/// Views or edits one memory. Editing has explicit Cancel and Save; leaving with unsaved text asks
/// first (the [OmiEditSheet] guard). Delete is immediate with an Undo toast.
class MemoryEditSheet extends StatefulWidget {
  final Memory memory;
  final MemoriesProvider provider;

  /// Called after the sheet deleted the memory and closed.
  final Function(BuildContext, Memory, MemoriesProvider)? onDelete;

  /// Show the memory without editing controls. Forced for memories that cannot be edited.
  final bool readOnly;

  const MemoryEditSheet(
      {super.key, required this.memory, required this.provider, this.onDelete, this.readOnly = false});

  @override
  State<MemoryEditSheet> createState() => _MemoryEditSheetState();
}

class _MemoryEditSheetState extends State<MemoryEditSheet> {
  late final TextEditingController contentController;
  late final String _originalContent;
  bool _isSaving = false;
  bool _saveFailed = false;
  late bool _isBaseline;

  bool get _readOnly => widget.readOnly || !memoryIsEditable(widget.memory);

  bool get _isDirty => !_readOnly && contentController.text.trim() != _originalContent.trim();

  @override
  void initState() {
    super.initState();
    _isBaseline = widget.memory.isBaseline;
    _originalContent = widget.memory.content.decodeString;
    contentController = TextEditingController(text: _originalContent);
    contentController.selection = TextSelection.fromPosition(TextPosition(offset: contentController.text.length));
  }

  @override
  void dispose() {
    contentController.dispose();
    super.dispose();
  }

  Future<void> _toggleBaseline() async {
    final newState = !_isBaseline;
    setState(() => _isBaseline = newState);

    final success = await widget.provider.toggleMemoryBaseline(widget.memory, newState);

    if (!success && mounted) {
      setState(() => _isBaseline = !newState);
      OmiFeedback.error(context, context.l10n.failedToUpdateBaselineStatus);
    }
  }

  void _delete() {
    unawaited(deleteMemoryWithUndo(context, widget.provider, widget.memory));
    Navigator.pop(context);
    widget.onDelete?.call(context, widget.memory, widget.provider);
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final memory = widget.memory;
    return OmiEditSheet(
      title: _readOnly ? l10n.memoryDetailsTitle : l10n.editMemoryTitle,
      isDirty: _isDirty,
      enabled: !_isSaving,
      actions: [
        if (!_readOnly) ...[
          OmiIconButton(
            icon: Icon(_isBaseline ? Icons.flag : Icons.flag_outlined),
            label: _isBaseline ? l10n.unpinAsBaseline : l10n.pinAsBaseline,
            onPressed: _isSaving ? null : _toggleBaseline,
          ),
          OmiIconButton(
            icon: const Icon(Icons.delete_outline),
            label: l10n.deleteMemory,
            isDestructive: true,
            onPressed: _isSaving ? null : _delete,
          ),
        ],
      ],
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Wrap(
              spacing: OmiSpacing.xs,
              runSpacing: OmiSpacing.xs,
              children: [
                _MemoryChip(icon: Icons.label_outline, label: memory.category.toString().split('.').last),
                if (_isBaseline) _MemoryChip(icon: Icons.flag, label: l10n.baselineMemory),
              ],
            ),
            const SizedBox(height: OmiSpacing.sm),
            if (_readOnly)
              SelectableText(memory.content.decodeString, style: OmiType.callout.copyWith(height: 1.4))
            else
              ConstrainedBox(
                constraints: const BoxConstraints(maxHeight: 250),
                child: TextField(
                  key: const ValueKey('memory_edit_field'),
                  controller: contentController,
                  enabled: !_isSaving,
                  onChanged: (_) => setState(() {}),
                  autofocus: true,
                  maxLines: null,
                  minLines: 3,
                  textInputAction: TextInputAction.newline,
                  keyboardType: TextInputType.multiline,
                  style: OmiType.callout.copyWith(height: 1.4),
                  cursorColor: OmiColors.accent,
                  decoration: const InputDecoration(
                    border: InputBorder.none,
                    contentPadding: EdgeInsets.zero,
                    isDense: true,
                  ),
                ),
              ),
            if (memory.ledgerSlot != null && memory.ledgerSlot!.trim().isNotEmpty) ...[
              const SizedBox(height: OmiSpacing.xs),
              Text(memory.ledgerSlot!, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
            ],
            // The list clips playbook bodies at three lines; here they are shown in full.
            if (memory.isLedgerPlaybook && (memory.ledgerBody ?? '').trim().isNotEmpty) ...[
              const SizedBox(height: OmiSpacing.sm),
              SelectableText(
                memory.ledgerBody!.trim(),
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
              ),
            ],
            if (_readOnly && !memory.isLocked && !memoryIsEditable(memory)) ...[
              const SizedBox(height: OmiSpacing.md),
              Text(l10n.memoryReadOnlyHint, style: OmiType.footnote.copyWith(color: OmiColors.textTertiary)),
            ],
            if (!_readOnly) ...[
              const SizedBox(height: OmiSpacing.lg),
              if (_saveFailed) ...[
                Semantics(
                  liveRegion: true,
                  child: Text(
                    l10n.failedToSaveMemory,
                    style: OmiType.footnote.copyWith(color: OmiColors.danger),
                    textAlign: TextAlign.center,
                  ),
                ),
                const SizedBox(height: OmiSpacing.xs),
              ],
              Row(
                children: [
                  Expanded(
                    child: OmiButton.secondary(
                      label: l10n.cancel,
                      expand: true,
                      onPressed: _isSaving ? null : () => Navigator.pop(context),
                    ),
                  ),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(
                    child: OmiButton(
                      key: const ValueKey('memory_edit_save'),
                      label: _saveFailed ? l10n.tryAgain : l10n.save,
                      expand: true,
                      isLoading: _isSaving,
                      onPressed: contentController.text.trim().isEmpty ? null : _handleSave,
                    ),
                  ),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }

  Future<void> _handleSave() async {
    if (_isSaving || contentController.text.trim().isEmpty || _readOnly) return;
    if (!_isDirty) {
      Navigator.pop(context, true);
      return;
    }

    setState(() {
      _isSaving = true;
      _saveFailed = false;
    });

    bool success;
    try {
      success = await widget.provider.editMemory(widget.memory, contentController.text.trim(), widget.memory.category);
    } catch (e) {
      success = false;
      Logger.debug('Error saving memory: $e');
    }

    if (!mounted) return;

    setState(() {
      _isSaving = false;
      _saveFailed = !success;
    });

    if (success) {
      OmiHaptics.light();
      OmiFeedback.confirm(context, context.l10n.saved);
      Navigator.pop(context, true);
    }
  }
}

class _MemoryChip extends StatelessWidget {
  const _MemoryChip({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 6),
      decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.pillAll),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: OmiColors.textSecondary),
          const SizedBox(width: OmiSpacing.xxs),
          Text(label, style: OmiType.footnote),
        ],
      ),
    );
  }
}
