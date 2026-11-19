import 'dart:async';

import 'package:flutter/widgets.dart';

import 'package:omi/ui/feedback/omi_feedback.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A setting applies when it changes (ux-contract §12), and a change the server refused comes back
/// with a message, never in silence (§17.4). Shows [next] at once through [show], saves it, and on
/// a failed save shows [previous] again and says so with Try Again. Resolves whether it saved.
Future<bool> applyOmiSetting<T>(
  BuildContext context, {
  required T previous,
  required T next,
  required void Function(T value) show,
  required Future<bool> Function(T value) save,
}) async {
  show(next);
  bool saved;
  try {
    saved = await save(next);
  } catch (_) {
    saved = false;
  }
  if (saved) return true;
  show(previous);
  if (context.mounted) {
    OmiFeedback.error(
      context,
      context.l10n.settingNotSaved,
      actionLabel: context.l10n.tryAgain,
      onAction: () {
        if (context.mounted) {
          unawaited(applyOmiSetting(context, previous: previous, next: next, show: show, save: save));
        }
      },
    );
  }
  return false;
}
