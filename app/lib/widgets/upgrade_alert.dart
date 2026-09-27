// Copyright (c) 2023 Larry Aasen. All rights reserved.

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:upgrader/upgrader.dart';

import 'package:omi/ui/feedback/omi_dialogs.dart';
import 'package:omi/ui/prompts/prompt_queue.dart';
import 'package:omi/utils/l10n_extensions.dart';

class MyUpgrader extends Upgrader {
  MyUpgrader({super.debugLogging, super.debugDisplayOnce});
}

class MyUpgradeAlert extends UpgradeAlert {
  MyUpgradeAlert({super.key, super.upgrader, super.child, super.dialogStyle});

  /// Override the [createState] method to provide a custom class
  /// with overridden methods.
  @override
  UpgradeAlertState createState() => MyUpgradeAlertState();
}

class MyUpgradeAlertState extends UpgradeAlertState {
  @override
  void showTheDialog({
    Key? key,
    required BuildContext context,
    required String? title,
    required String message,
    required String? releaseNotes,
    required bool barrierDismissible,
    required UpgraderMessages messages,
  }) {
    // "Not Now" postpones (onUserLater); it never silences this version forever (onUserIgnored).
    // Queued with the other startup prompts: one at a time, never over a recording or a call. A
    // required update (upgrader "blocked") goes first.
    PromptQueue.instance.enqueue(
      'upgrade-alert',
      widget.upgrader.blocked() ? PromptPriority.critical : PromptPriority.normal,
      show: (promptContext) => _show(promptContext, key: key, message: message, barrierDismissible: barrierDismissible),
    );
  }

  Future<void> _show(
    BuildContext context, {
    Key? key,
    required String message,
    required bool barrierDismissible,
  }) {
    return showDialog<void>(
      context: context,
      barrierDismissible: barrierDismissible,
      builder: (BuildContext context) => OmiAlertDialog(
        key: key,
        title: context.l10n.newVersionAvailable,
        message: message,
        actions: [
          OmiDialogAction(
            label: context.l10n.notNow,
            onPressed: () {
              onUserLater(context, true);
              PlatformManager.instance.analytics.upgradeModalDismissed();
            },
          ),
          OmiDialogAction(
            label: context.l10n.update,
            isDefault: true,
            onPressed: () {
              onUserUpdated(context, !widget.upgrader.blocked());
              PlatformManager.instance.analytics.upgradeModalClicked();
            },
          ),
        ],
      ),
    );
  }
}
