import 'package:flutter/material.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/ui/feedback/omi_dialogs.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Legacy context-free adapter over [OmiAlertDialog], for providers and services that only have
/// the global navigator. Code with a `BuildContext` calls `showOmiConfirm` / `showOmiAlert`.
///
/// Every button closes the dialog after running its callback. With [singleButton] the dialog is an
/// information alert: one [okButtonText] (default OK) that runs [onCancel].
class AppDialog {
  static void show({
    required String title,
    required String content,
    Function? onConfirm,
    Function? onCancel,
    bool singleButton = false,
    String? okButtonText,
    bool destructive = false,
  }) {
    final state = globalNavigatorKey.currentState;
    if (state == null || state.overlay == null) return;
    showDialog(
      context: state.overlay!.context,
      builder: (dialogContext) {
        void run(Function? callback) {
          final route = ModalRoute.of(dialogContext);
          callback?.call();
          if (dialogContext.mounted && route != null && route.isCurrent) Navigator.of(dialogContext).pop();
        }

        final okText = okButtonText ?? dialogContext.l10n.ok;
        return OmiAlertDialog(
          title: title,
          message: content,
          actions: singleButton
              ? [OmiDialogAction(label: okText, isDefault: true, onPressed: () => run(onCancel))]
              : [
                  OmiDialogAction(
                    label: dialogContext.l10n.cancel,
                    isDefault: destructive,
                    onPressed: () => run(onCancel),
                  ),
                  OmiDialogAction(
                    label: okText,
                    isDestructive: destructive,
                    isDefault: !destructive,
                    onPressed: () => run(onConfirm),
                  ),
                ],
        );
      },
    );
  }
}
