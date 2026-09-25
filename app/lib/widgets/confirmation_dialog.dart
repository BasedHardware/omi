import 'package:flutter/widgets.dart';

import 'package:omi/ui/feedback/omi_dialogs.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Legacy adapter over [OmiAlertDialog]; new code calls `showOmiConfirm` /
/// `showOmiConfirmWithOptOut` (docs/ux-contract.md §4).
///
/// Cancel is always shown ([cancelText], default "Cancel"). If [onCancel] does not close the
/// dialog itself, Cancel closes it anyway, so a question can never be left with one answer. A
/// dialog with only one sensible answer is an alert: use `showOmiAlert`.
///
/// [checkboxText] adds a tappable "Don't ask again" row. Set [destructive] when [confirmText]
/// destroys something.
class ConfirmationDialog extends StatefulWidget {
  final String title;
  final String description;
  final String? checkboxText;
  final bool? checkboxValue;
  final void Function(bool value)? onCheckboxChanged;
  final String? cancelText;
  final String? confirmText;
  final void Function() onConfirm;
  final void Function() onCancel;
  final bool destructive;

  const ConfirmationDialog({
    super.key,
    required this.title,
    required this.description,
    this.checkboxText,
    this.checkboxValue,
    this.onCheckboxChanged,
    this.cancelText,
    this.confirmText,
    required this.onConfirm,
    required this.onCancel,
    this.destructive = false,
  });

  @override
  State<ConfirmationDialog> createState() => _ConfirmationDialogState();
}

class _ConfirmationDialogState extends State<ConfirmationDialog> {
  bool _checkboxValue = false;

  @override
  void initState() {
    super.initState();
    _checkboxValue = widget.checkboxValue ?? false;
  }

  void _updateCheckboxValue(bool value) {
    setState(() => _checkboxValue = value);
    widget.onCheckboxChanged?.call(value);
  }

  void _cancel() {
    final route = ModalRoute.of(context);
    widget.onCancel();
    // Callers written for the old widget sometimes pass a no-op onCancel; Cancel must still close.
    if (mounted && route != null && route.isCurrent) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final checkboxText = widget.checkboxText;
    return OmiAlertDialog(
      title: widget.title,
      message: widget.description,
      content: checkboxText != null && checkboxText.isNotEmpty
          ? OmiCheckboxRow(label: checkboxText, value: _checkboxValue, onChanged: _updateCheckboxValue)
          : null,
      actions: [
        OmiDialogAction(
          label: widget.cancelText ?? context.l10n.cancel,
          isDefault: widget.destructive,
          onPressed: _cancel,
        ),
        OmiDialogAction(
          label: widget.confirmText ?? context.l10n.confirm,
          isDestructive: widget.destructive,
          isDefault: !widget.destructive,
          onPressed: widget.onConfirm,
        ),
      ],
    );
  }
}
