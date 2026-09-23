import 'package:flutter/widgets.dart';

import 'package:omi/ui/feedback/omi_dialogs.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Legacy adapter over [OmiAlertDialog]; new code calls `showOmiConfirm` / `showOmiAlert`
/// (docs/ux-contract.md §4).
///
/// Two buttons: Cancel ([onCancel]) and [okButtonText] ([onConfirm]); pass a verb for
/// [okButtonText] ("Delete", "Sign Out") and set [destructive] when the action destroys something.
/// With [singleButton] it is an information alert whose one button ([okButtonText], default OK)
/// calls [onCancel]. Callers pop the dialog themselves in both callbacks.
Widget getDialog(
  BuildContext context,
  Function onCancel,
  Function onConfirm,
  String title,
  String content, {
  bool singleButton = false,
  String? okButtonText,
  String? cancelButtonText,
  bool destructive = false,
}) {
  final okText = okButtonText ?? context.l10n.ok;
  final cancelText = cancelButtonText ?? context.l10n.cancel;
  return OmiAlertDialog(
    title: title,
    message: content,
    actions: singleButton
        ? [OmiDialogAction(label: okText, isDefault: true, onPressed: () => onCancel())]
        : [
            OmiDialogAction(label: cancelText, isDefault: destructive, onPressed: () => onCancel()),
            OmiDialogAction(
              label: okText,
              isDestructive: destructive,
              isDefault: !destructive,
              onPressed: () => onConfirm(),
            ),
          ],
  );
}
