import 'package:flutter/material.dart';

import 'package:omi/ui/omi_tokens.dart';

import 'package:omi/utils/l10n_extensions.dart';

/// How long each kind of feedback stays up (docs/ux-contract.md §6).
abstract final class OmiFeedbackTiming {
  /// "Saved", "Copied": the reader just did it and only needs to see it landed.
  static const confirm = Duration(milliseconds: 1500);

  /// Something happened that the reader did not directly cause.
  static const info = Duration(seconds: 4);

  /// Deferred deletes. Providers that hold a server delete back must hold it at least this long.
  static const undo = Duration(seconds: 5);

  /// Errors carry a close button and stay this long unless dismissed.
  static const error = Duration(seconds: 8);

  /// Ongoing work ("Exporting…"); replaced by the result, or gone after this.
  static const progress = Duration(minutes: 1);
}

enum OmiFeedbackKind { confirm, info, error, undo, progress }

const Color _successIconColor = OmiColors.success;
const Color _errorIconColor = OmiColors.danger;
const Color _infoIconColor = OmiColors.textSecondary;

/// The app's one toast system: a floating, neutral snackbar with a small coloured status icon.
///
/// * One at a time: showing feedback hides whatever is up (an [undo] being replaced resolves
///   "not undone", so its caller commits).
/// * The surface stays neutral (the theme's snackbar colour); colour lives on the icon only, so
///   text keeps its contrast.
/// * Floating, clear of the home shell's tab bar and chat bar via [bottomClearance].
///
/// ```dart
/// OmiFeedback.confirm(context, l10n.memoryUpdated);
/// final undone = await OmiFeedback.undo(context, l10n.actionItemDeleted, onUndo: restore);
/// if (!undone) await provider.commitDelete(id);
/// ```
abstract final class OmiFeedback {
  /// Extra space the home shell needs above the safe area while it is the visible route (its tab
  /// bar, and the chat bar on Home). The shell sets this in `initState` and clears it in `dispose`;
  /// it is ignored whenever another route is on top.
  static double Function(BuildContext context)? bottomClearance;

  /// Confirms something the reader just did. 1.5 s.
  static void confirm(BuildContext context, String message) =>
      _show(context, message, kind: OmiFeedbackKind.confirm, duration: OmiFeedbackTiming.confirm);

  /// Tells the reader something they did not directly cause. 4 s.
  static void info(BuildContext context, String message) =>
      _show(context, message, kind: OmiFeedbackKind.info, duration: OmiFeedbackTiming.info);

  /// Reports a failure. Stays 8 s with a close button, or until [onAction] ("Try Again").
  static void error(BuildContext context, String message, {String? actionLabel, VoidCallback? onAction}) => _show(
        context,
        message,
        kind: OmiFeedbackKind.error,
        duration: OmiFeedbackTiming.error,
        actionLabel: actionLabel,
        onAction: onAction,
        showClose: true,
      );

  /// Shows ongoing work until the next feedback replaces it (at most a minute).
  static void progress(BuildContext context, String message) =>
      _show(context, message, kind: OmiFeedbackKind.progress, duration: OmiFeedbackTiming.progress);

  /// Offers Undo for 5 s. Resolves `true` if the reader tapped Undo (after [onUndo] ran), `false`
  /// when it timed out, was swiped away or was replaced — the caller commits the delete then.
  ///
  /// There is deliberately no close button: nothing on an undo toast means "destroy this sooner".
  static Future<bool> undo(BuildContext context, String message, {required VoidCallback onUndo}) async {
    final controller = _show(
      context,
      message,
      kind: OmiFeedbackKind.undo,
      duration: OmiFeedbackTiming.undo,
      actionLabel: context.l10n.undo,
      onAction: onUndo,
    );
    if (controller == null) return false;
    final reason = await controller.closed;
    return reason == SnackBarClosedReason.action;
  }

  /// Hides whatever feedback is showing.
  static void hide(BuildContext context) => ScaffoldMessenger.maybeOf(context)?.hideCurrentSnackBar();

  static ScaffoldFeatureController<SnackBar, SnackBarClosedReason>? _show(
    BuildContext context,
    String message, {
    required OmiFeedbackKind kind,
    required Duration duration,
    String? actionLabel,
    VoidCallback? onAction,
    bool showClose = false,
  }) {
    final messenger = ScaffoldMessenger.maybeOf(context);
    if (messenger == null) return null;
    messenger.hideCurrentSnackBar();
    return messenger.showSnackBar(
      buildSnackBar(
        context,
        message,
        kind: kind,
        duration: duration,
        actionLabel: actionLabel,
        onAction: onAction,
        showClose: showClose,
      ),
    );
  }

  /// The snackbar [OmiFeedback] shows; public for tests and for [ScaffoldMessenger] owners that
  /// must show it themselves.
  static SnackBar buildSnackBar(
    BuildContext context,
    String message, {
    required OmiFeedbackKind kind,
    required Duration duration,
    String? actionLabel,
    VoidCallback? onAction,
    bool showClose = false,
  }) {
    return SnackBar(
      behavior: SnackBarBehavior.floating,
      margin: EdgeInsets.fromLTRB(16, 0, 16, 12 + _extraBottom(context)),
      duration: duration,
      // Flutter persists any snackbar with an action unless told otherwise; ours time out, or an
      // Undo would never commit its delete.
      persist: false,
      showCloseIcon: showClose,
      closeIconColor: Colors.white70,
      dismissDirection: DismissDirection.down,
      content: Semantics(
        liveRegion: true,
        child: Row(
          children: [
            _icon(kind),
            const SizedBox(width: 12),
            Expanded(child: Text(message)),
          ],
        ),
      ),
      action: actionLabel != null && onAction != null
          ? SnackBarAction(label: actionLabel, textColor: Colors.white, onPressed: onAction)
          : null,
    );
  }

  static double _extraBottom(BuildContext context) {
    final clearance = bottomClearance;
    if (clearance == null) return 0;
    final navigator = Navigator.maybeOf(context, rootNavigator: true);
    if (navigator == null || navigator.canPop()) return 0;
    return clearance(navigator.context);
  }

  static Widget _icon(OmiFeedbackKind kind) {
    return switch (kind) {
      OmiFeedbackKind.confirm => const Icon(Icons.check_circle_rounded, size: 20, color: _successIconColor),
      OmiFeedbackKind.error => const Icon(Icons.error_rounded, size: 20, color: _errorIconColor),
      OmiFeedbackKind.undo => const Icon(Icons.delete_outline_rounded, size: 20, color: _infoIconColor),
      OmiFeedbackKind.info => const Icon(Icons.info_outline_rounded, size: 20, color: _infoIconColor),
      OmiFeedbackKind.progress => const SizedBox.square(
          dimension: 20,
          child: Padding(
            padding: EdgeInsets.all(2),
            child: CircularProgressIndicator(strokeWidth: 2, color: _infoIconColor),
          ),
        ),
    };
  }
}
