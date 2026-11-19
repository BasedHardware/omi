import 'dart:async';

import 'package:flutter/widgets.dart';

import 'package:omi/ui/feedback/omi_feedback.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// A setting applies when it changes (ux-contract §12), and a change the server refused comes back
/// with a message, never in silence (§17.4). Shows [next] at once through [show], saves it, and on
/// a failed save shows [previous] again and says so with Try Again. Resolves whether it saved.
///
/// [setting] names the setting: when a newer change to the same setting was made while this save
/// was in flight, a late failure here neither rolls back nor reports, so it cannot undo the newer
/// choice.
Future<bool> applyOmiSetting<T>(
  BuildContext context, {
  required Object setting,
  required T previous,
  required T next,
  required void Function(T value) show,
  required Future<bool> Function(T value) save,
}) async {
  final write = (_latestWrite[setting] ?? 0) + 1;
  _latestWrite[setting] = write;
  show(next);
  bool saved;
  try {
    saved = await save(next);
  } catch (_) {
    saved = false;
  }
  if (saved) return true;
  if (_latestWrite[setting] != write) return false; // superseded by a newer change
  show(previous);
  if (context.mounted) {
    OmiFeedback.error(
      context,
      context.l10n.settingNotSaved,
      actionLabel: context.l10n.tryAgain,
      onAction: () {
        if (context.mounted) {
          unawaited(applyOmiSetting(context, setting: setting, previous: previous, next: next, show: show, save: save));
        }
      },
    );
  }
  return false;
}

final Map<Object, int> _latestWrite = {};
