import 'dart:async';

import 'package:flutter/material.dart';

import 'package:omi/app_globals.dart';
import 'package:omi/mobile/native_ui/ios_native_modal.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/ui/feedback/omi_dialogs.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Legacy context-free adapter over [OmiAlertDialog], for providers and services that only have
/// the global navigator. Code with a `BuildContext` calls `showOmiConfirm` / `showOmiAlert`.
///
/// Every button closes the dialog after running its callback. With [singleButton] the dialog is an
/// information alert: one [okButtonText] (default OK) that runs [onCancel].
///
/// With the native presentation it is a system alert first: OK (or Cancel) runs [onCancel], the
/// confirm button runs [onConfirm], and leaving it any other way runs nothing, like a scrim tap.
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
    void classic(BuildContext context) => _showFlutter(context,
        title: title,
        content: content,
        onConfirm: onConfirm,
        onCancel: onCancel,
        singleButton: singleButton,
        okButtonText: okButtonText,
        destructive: destructive);
    if (!nativePresentationEnabled) return classic(state.overlay!.context);
    unawaited(_showNative(state.overlay!.context,
        title: title,
        content: content,
        onConfirm: onConfirm,
        onCancel: onCancel,
        singleButton: singleButton,
        okButtonText: okButtonText,
        destructive: destructive,
        fallback: classic));
  }

  static Future<void> _showNative(
    BuildContext context, {
    required String title,
    required String content,
    required Function? onConfirm,
    required Function? onCancel,
    required bool singleButton,
    required String? okButtonText,
    required bool destructive,
    required void Function(BuildContext context) fallback,
  }) async {
    final l10n = context.l10n;
    final okText = okButtonText ?? l10n.ok;
    final result = await showIosNativeModal(context,
        title: title,
        alert: true,
        cancelId: singleButton ? 'acknowledge' : 'cancel',
        actions: singleButton
            ? [NativeRow('acknowledge', okText)]
            : [
                NativeRow('cancel', l10n.cancel, symbol: 'xmark'),
                NativeRow('confirm', okText, destructive: destructive),
              ],
        sections: [
          if (content.isNotEmpty) NativeSection('message', [NativeRow('message', content, kind: 'label')]),
        ]);
    if (result == null) {
      // The native alert was not used: the complete Flutter dialog, on the overlay that is current now.
      final overlay = globalNavigatorKey.currentState?.overlay;
      if (overlay != null && overlay.mounted) fallback(overlay.context);
      return;
    }
    if (result.action == 'confirm') {
      onConfirm?.call();
    } else if (result.reason == 'cancel') {
      onCancel?.call();
    }
  }

  static void _showFlutter(
    BuildContext context, {
    required String title,
    required String content,
    required Function? onConfirm,
    required Function? onCancel,
    required bool singleButton,
    required String? okButtonText,
    required bool destructive,
  }) {
    showDialog(
      context: context,
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
