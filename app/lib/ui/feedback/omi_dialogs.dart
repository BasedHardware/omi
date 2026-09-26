import 'package:flutter/cupertino.dart';
import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

import 'package:omi/utils/l10n_extensions.dart';

/// The app's single confirmation / alert system (docs/ux-contract.md §5).
///
/// * [showOmiConfirm] — a question with two answers: Cancel and a verb that names the action
///   ("Delete", "Sign Out", "Clear Chat"). Cancel is always shown.
/// * [showOmiConfirmWithOptOut] — the same, plus a "Don't ask again" row. Only for actions an Undo
///   backs; an action that cannot be undone is confirmed every time.
/// * [showOmiAlert] — information with one button.
/// * [OmiAlertDialog] — the widget behind all three, for code that has to hand `showDialog` a
///   widget (the legacy `getDialog` / `ConfirmationDialog` adapters).
///
/// On iOS the dialog is a `CupertinoAlertDialog` with real `CupertinoDialogAction`s (destructive
/// actions red, the safe choice bold); elsewhere a Material `AlertDialog` with text buttons, the
/// destructive one in [omiDialogDangerColor].

/// Destructive action colour on Material dialogs (iOS dark-mode systemRed; legible on every dark surface).
const Color omiDialogDangerColor = OmiColors.danger;

/// One button in an [OmiAlertDialog].
class OmiDialogAction {
  const OmiDialogAction({
    this.key,
    required this.label,
    required this.onPressed,
    this.isDestructive = false,
    this.isDefault = false,
  });

  /// Identifies the rendered action button in tests.
  final Key? key;

  /// A verb naming what the button does ("Delete", "Sign Out"), or Cancel / OK.
  final String label;
  final VoidCallback? onPressed;

  /// Red: the action destroys something.
  final bool isDestructive;

  /// Bold on iOS: the action a reader is expected to take (Cancel, when the other choice is destructive).
  final bool isDefault;
}

/// Whether dialogs on this [context] use the Cupertino look.
///
/// Reads the theme's platform (not `dart:io`) so tests can pin it with `debugDefaultTargetPlatformOverride`.
bool omiUsesCupertinoDialogs(BuildContext context) {
  final platform = Theme.of(context).platform;
  return platform == TargetPlatform.iOS || platform == TargetPlatform.macOS;
}

/// The adaptive alert dialog every Omi confirmation and alert is drawn with.
class OmiAlertDialog extends StatelessWidget {
  const OmiAlertDialog({super.key, this.title, this.message, this.content, required this.actions});

  final String? title;
  final String? message;

  /// Extra content below [message] (e.g. a "Don't ask again" row).
  final Widget? content;
  final List<OmiDialogAction> actions;

  @override
  Widget build(BuildContext context) {
    final body = _body(context);
    if (omiUsesCupertinoDialogs(context)) {
      return CupertinoAlertDialog(
        title: title == null ? null : Text(title!),
        content: body,
        actions: [
          for (final action in actions)
            CupertinoDialogAction(
              key: action.key,
              onPressed: action.onPressed,
              isDestructiveAction: action.isDestructive,
              isDefaultAction: action.isDefault,
              child: Text(action.label),
            ),
        ],
      );
    }
    return AlertDialog(
      scrollable: true,
      title: title == null ? null : Text(title!),
      content: body,
      actions: [
        for (final action in actions)
          TextButton(
            key: action.key,
            onPressed: action.onPressed,
            style: TextButton.styleFrom(
              foregroundColor: action.isDestructive
                  ? omiDialogDangerColor
                  : (action.isDefault ? Colors.white : Colors.white.withValues(alpha: 0.78)),
              minimumSize: const Size(64, 44),
            ),
            child: Text(
              action.label,
              style: TextStyle(fontWeight: action.isDefault || action.isDestructive ? FontWeight.w600 : null),
            ),
          ),
      ],
    );
  }

  Widget? _body(BuildContext context) {
    if (message == null && content == null) return null;
    if (content == null) return Text(message!);
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: omiUsesCupertinoDialogs(context) ? CrossAxisAlignment.center : CrossAxisAlignment.start,
      children: [
        if (message != null) Text(message!),
        if (message != null) const SizedBox(height: 12),
        content!,
      ],
    );
  }
}

/// Result of [showOmiConfirmWithOptOut].
class OmiConfirmResult {
  const OmiConfirmResult({required this.confirmed, required this.dontAskAgain});

  final bool confirmed;

  /// The reader ticked "Don't ask again". Only meaningful when [confirmed]; callers persist it then.
  final bool dontAskAgain;
}

/// Asks [title] with Cancel and [confirmLabel]. Resolves `true` only when the reader chose
/// [confirmLabel]; Cancel, the barrier and system back all resolve `false`.
///
/// [confirmLabel] is a verb naming the action ("Delete", "Sign Out", "Clear Chat"), never "OK" or
/// "Confirm". Set [destructive] when the action destroys something: the button turns red and
/// Cancel becomes the default (bold) choice.
Future<bool> showOmiConfirm(
  BuildContext context, {
  required String title,
  String? message,
  required String confirmLabel,
  bool destructive = false,
  String? cancelLabel,
  bool barrierDismissible = true,
}) async {
  final confirmed = await showDialog<bool>(
    context: context,
    barrierDismissible: barrierDismissible,
    builder: (dialogContext) => OmiAlertDialog(
      title: title,
      message: message,
      actions: _confirmActions(
        dialogContext,
        confirmLabel: confirmLabel,
        cancelLabel: cancelLabel,
        destructive: destructive,
        onCancel: () => Navigator.of(dialogContext).pop(false),
        onConfirm: () => Navigator.of(dialogContext).pop(true),
      ),
    ),
  );
  return confirmed ?? false;
}

/// [showOmiConfirm] with a "Don't ask again" row under the message.
///
/// Contract: offer this only when an Undo backs the action (docs/ux-contract.md §4). The row is a
/// single ≥44pt target — tapping the label toggles it too.
Future<OmiConfirmResult> showOmiConfirmWithOptOut(
  BuildContext context, {
  required String title,
  String? message,
  required String confirmLabel,
  bool destructive = false,
  String? cancelLabel,
  String? optOutLabel,
  bool initialOptOut = false,
  bool barrierDismissible = true,
}) async {
  var dontAskAgain = initialOptOut;
  final confirmed = await showDialog<bool>(
    context: context,
    barrierDismissible: barrierDismissible,
    builder: (dialogContext) => StatefulBuilder(
      builder: (dialogContext, setState) => OmiAlertDialog(
        title: title,
        message: message,
        content: OmiCheckboxRow(
          label: optOutLabel ?? dialogContext.l10n.dontAskAgain,
          value: dontAskAgain,
          onChanged: (value) => setState(() => dontAskAgain = value),
        ),
        actions: _confirmActions(
          dialogContext,
          confirmLabel: confirmLabel,
          cancelLabel: cancelLabel,
          destructive: destructive,
          onCancel: () => Navigator.of(dialogContext).pop(false),
          onConfirm: () => Navigator.of(dialogContext).pop(true),
        ),
      ),
    ),
  );
  return OmiConfirmResult(confirmed: confirmed ?? false, dontAskAgain: dontAskAgain);
}

/// Information with one button ([okLabel], default "OK"). Resolves when it closes.
Future<void> showOmiAlert(
  BuildContext context, {
  required String title,
  String? message,
  String? okLabel,
  bool barrierDismissible = true,
}) {
  return showDialog<void>(
    context: context,
    barrierDismissible: barrierDismissible,
    builder: (dialogContext) => OmiAlertDialog(
      title: title,
      message: message,
      actions: [
        OmiDialogAction(
          label: okLabel ?? dialogContext.l10n.ok,
          isDefault: true,
          onPressed: () => Navigator.of(dialogContext).pop(),
        ),
      ],
    ),
  );
}

List<OmiDialogAction> _confirmActions(
  BuildContext context, {
  required String confirmLabel,
  required String? cancelLabel,
  required bool destructive,
  required VoidCallback onCancel,
  required VoidCallback onConfirm,
}) {
  return [
    OmiDialogAction(label: cancelLabel ?? context.l10n.cancel, isDefault: destructive, onPressed: onCancel),
    OmiDialogAction(label: confirmLabel, isDestructive: destructive, isDefault: !destructive, onPressed: onConfirm),
  ];
}

/// A checkbox with its label as one ≥44pt tappable row (the label toggles it too).
class OmiCheckboxRow extends StatelessWidget {
  const OmiCheckboxRow({super.key, required this.label, required this.value, required this.onChanged});

  final String label;
  final bool value;
  final ValueChanged<bool> onChanged;

  @override
  Widget build(BuildContext context) {
    final cupertino = omiUsesCupertinoDialogs(context);
    return MergeSemantics(
      child: Semantics(
        checked: value,
        // GestureDetector, not InkWell: CupertinoAlertDialog has no Material ancestor.
        child: GestureDetector(
          behavior: HitTestBehavior.opaque,
          onTap: () => onChanged(!value),
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 44),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                ExcludeSemantics(
                  child: cupertino
                      ? CupertinoCheckbox(
                          value: value,
                          onChanged: (v) => onChanged(v ?? false),
                          activeColor: Colors.white,
                          checkColor: CupertinoColors.black,
                        )
                      : Checkbox(
                          value: value,
                          onChanged: (v) => onChanged(v ?? false),
                          activeColor: Colors.white,
                          checkColor: Colors.black,
                        ),
                ),
                const SizedBox(width: 4),
                Flexible(child: Text(label, textAlign: TextAlign.start)),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
