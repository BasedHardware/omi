import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/memory.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/logger.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'memory_delete_undo.dart';
import 'memory_edit_sheet.dart';

/// The new-memory sheet. With [memory] it edits that memory instead (prefer
/// [showMemoryQuickEditSheet] for existing memories: it also opens read-only ones).
class MemoryDialog extends StatefulWidget {
  final MemoriesProvider provider;
  final Memory? memory;

  const MemoryDialog({super.key, required this.provider, this.memory});

  @override
  State<MemoryDialog> createState() => _MemoryDialogState();
}

class _MemoryDialogState extends State<MemoryDialog> {
  late TextEditingController contentController;
  bool _isSaving = false;
  bool _saveFailed = false;

  bool get _isEditing => widget.memory != null;

  bool get _isDirty => contentController.text.trim() != (widget.memory?.content ?? '').trim();

  @override
  void initState() {
    super.initState();
    contentController = TextEditingController(text: widget.memory?.content ?? '');
    contentController.selection = TextSelection.fromPosition(TextPosition(offset: contentController.text.length));
  }

  @override
  void dispose() {
    contentController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return OmiEditSheet(
      title: _isEditing ? l10n.editMemoryTitle : l10n.newMemoryTitle,
      isDirty: _isDirty,
      enabled: !_isSaving,
      actions: [
        if (_isEditing)
          OmiIconButton(
            icon: const Icon(Icons.delete_outline),
            label: l10n.deleteMemory,
            isDestructive: true,
            onPressed: _isSaving ? null : _delete,
          ),
      ],
      child: SingleChildScrollView(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 250),
              child: TextField(
                key: const ValueKey('memory_content_field'),
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
                decoration: InputDecoration(
                  hintText: _isEditing ? null : l10n.memoryContentHint,
                  hintStyle: OmiType.callout.copyWith(color: OmiColors.textTertiary),
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.zero,
                  isDense: true,
                ),
              ),
            ),
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
                    key: const ValueKey('memory_save_button'),
                    label: _saveFailed ? l10n.tryAgain : l10n.save,
                    expand: true,
                    isLoading: _isSaving,
                    onPressed: contentController.text.trim().isEmpty ? null : _handleSave,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  void _delete() {
    final memory = widget.memory;
    if (memory == null) return;
    unawaited(deleteMemoryWithUndo(context, widget.provider, memory));
    Navigator.pop(context);
  }

  Future<void> _handleSave() async {
    if (_isSaving || contentController.text.trim().isEmpty) return;
    final existingMemory = widget.memory;
    if (existingMemory != null && !memoryIsEditable(existingMemory)) return;

    setState(() {
      _isSaving = true;
      _saveFailed = false;
    });

    final previousIds = widget.provider.memories.map((memory) => memory.id).toSet();
    bool success;

    try {
      if (existingMemory != null) {
        success = await widget.provider.editMemory(existingMemory, contentController.text.trim());
        if (success) {
          PlatformManager.instance.analytics.memoriesPageEditedMemory();
        }
      } else {
        success = await widget.provider.createMemory(
          contentController.text.trim(),
          MemoryVisibility.private,
          MemoryCategory.manual,
        );
        if (success) {
          PlatformManager.instance.analytics.memoriesPageCreatedMemory(MemoryCategory.manual);
        }
      }
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
      final waitingToSync = existingMemory == null &&
          SharedPreferencesUtil().pendingMemories.any((memory) => !previousIds.contains(memory.id));
      OmiFeedback.confirm(
        context,
        waitingToSync ? '${context.l10n.saved} · ${context.l10n.syncStatusWaiting}' : context.l10n.saved,
      );
      Navigator.pop(context, true);
    }
  }
}

/// Opens the new-memory sheet, or — with [memory] — that memory (editable or read-only).
/// Resolves `true` when something was saved.
Future<bool?> showMemoryDialog(BuildContext context, MemoriesProvider provider, {Memory? memory}) async {
  if (memory != null) {
    await showMemoryQuickEditSheet(context, memory, provider);
    return null;
  }
  return showOmiEditSheet<bool>(
    context: context,
    builder: (context) => MemoryDialog(provider: provider),
  );
}
