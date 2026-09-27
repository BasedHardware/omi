import 'package:flutter/material.dart';

import 'package:omi/ui/feedback/omi_dialogs.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Legacy adapter over `showOmiConfirm`; new code calls that directly (docs/ux-contract.md §4).
///
/// Labels default to the localized "Confirm" / "Cancel"; pass a verb for [confirmLabel]. The
/// dialog is adaptive (Cupertino on iOS). [destructive] marks the confirm button red; when it is
/// not given it is inferred from [confirmColor] (anything but white counts as destructive, which
/// matches every existing caller: red/orange for delete, clear and cancel-sync, white for sync).
class OmiConfirmDialog {
  static Future<bool?> show(
    BuildContext context, {
    required String title,
    required String message,
    String? confirmLabel,
    String? cancelLabel,
    Color? confirmColor,
    bool? destructive,
  }) {
    return showOmiConfirm(
      context,
      title: title,
      message: message,
      confirmLabel: confirmLabel ?? context.l10n.confirm,
      cancelLabel: cancelLabel,
      destructive: destructive ?? _isDestructiveColor(confirmColor),
    );
  }

  static Future<ConfirmationResult?> showWithSkipOption(
    BuildContext context, {
    required String title,
    required String message,
    String? confirmLabel,
    String? cancelLabel,
    String? skipLabel,
    Color? confirmColor,
    bool? destructive,
  }) async {
    final result = await showOmiConfirmWithOptOut(
      context,
      title: title,
      message: message,
      confirmLabel: confirmLabel ?? context.l10n.confirm,
      cancelLabel: cancelLabel,
      optOutLabel: skipLabel ?? context.l10n.dontShowAgain,
      destructive: destructive ?? _isDestructiveColor(confirmColor),
    );
    return ConfirmationResult(confirmed: result.confirmed, skipFutureConfirmations: result.dontAskAgain);
  }

  static bool _isDestructiveColor(Color? color) => color == null || color.toARGB32() != Colors.white.toARGB32();
}

class ConfirmationResult {
  final bool confirmed;
  final bool skipFutureConfirmations;

  const ConfirmationResult({required this.confirmed, required this.skipFutureConfirmations});
}
