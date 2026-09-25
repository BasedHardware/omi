import 'package:flutter/material.dart';

import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Opens the sheet that corrects one transcript line's text.
///
/// Titled with the line's speaker ([speakerName] comes from `SpeakerNames`, so the reader's own
/// lines say "You"). Save and Cancel are explicit; leaving with unsaved text (Cancel, swipe-down,
/// the scrim or system back) asks before discarding it.
Future<void> showEditSegmentBottomSheet(
  BuildContext context, {
  required TranscriptSegment segment,
  required String speakerName,
  required Function(String newText) onSave,
  VoidCallback? onDismissed,
}) {
  return showOmiSheet<void>(
    context: context,
    title: speakerName,
    builder: (_) => EditSegmentSheet(segment: segment, onSave: onSave),
  ).whenComplete(() => onDismissed?.call());
}

/// Body of the edit-segment sheet; present it with [showEditSegmentBottomSheet].
class EditSegmentSheet extends StatefulWidget {
  final TranscriptSegment segment;
  final Function(String newText) onSave;

  const EditSegmentSheet({super.key, required this.segment, required this.onSave});

  @override
  State<EditSegmentSheet> createState() => _EditSegmentSheetState();
}

class _EditSegmentSheetState extends State<EditSegmentSheet> {
  late final TextEditingController _controller;
  bool _dirty = false;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.segment.text);
    _controller.addListener(_onChanged);
  }

  @override
  void dispose() {
    _controller.removeListener(_onChanged);
    _controller.dispose();
    super.dispose();
  }

  void _onChanged() {
    final dirty = _controller.text.trim() != widget.segment.text.trim();
    if (dirty != _dirty) setState(() => _dirty = dirty);
  }

  void _save() {
    final newText = _controller.text.trim();
    if (newText.isNotEmpty && newText != widget.segment.text) {
      widget.onSave(newText);
    }
    _dirty = false;
    Navigator.of(context).pop();
  }

  Future<void> _confirmDiscard() async {
    final l10n = context.l10n;
    final discard = await showOmiConfirm(
      context,
      title: l10n.discardChangesTitle,
      message: l10n.discardChangesMessage,
      confirmLabel: l10n.discard,
      cancelLabel: l10n.keepEditing,
      destructive: true,
    );
    if (!discard || !mounted) return;
    setState(() => _dirty = false);
    Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: !_dirty,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _confirmDiscard();
      },
      child: SingleChildScrollView(
        child: Padding(
          padding: const EdgeInsets.only(bottom: OmiSpacing.md),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (widget.segment.start > 0)
                Padding(
                  padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
                  child: Text(
                    OmiDuration.offset(widget.segment.start),
                    style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                  ),
                ),
              TextField(
                controller: _controller,
                autofocus: true,
                maxLines: null,
                minLines: 3,
                style: OmiType.subhead.copyWith(height: 1.5),
                decoration: const InputDecoration(
                  filled: true,
                  fillColor: OmiColors.surface2,
                  border: OutlineInputBorder(borderRadius: OmiRadius.mdAll, borderSide: BorderSide.none),
                  contentPadding: EdgeInsets.all(14),
                ),
              ),
              const SizedBox(height: OmiSpacing.md),
              Row(
                children: [
                  Expanded(
                    child: OmiButton.secondary(
                      label: context.l10n.cancel,
                      expand: true,
                      onPressed: () => Navigator.of(context).maybePop(),
                    ),
                  ),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(child: OmiButton(label: context.l10n.save, expand: true, onPressed: _save)),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
