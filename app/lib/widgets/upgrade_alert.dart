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
      show: (promptContext) =>
          _show(promptContext, key: key, releaseNotes: releaseNotes, barrierDismissible: barrierDismissible),
    );
  }

  Future<void> _show(
    BuildContext context, {
    Key? key,
    required String? releaseNotes,
    required bool barrierDismissible,
  }) {
    final required = widget.upgrader.blocked();
    return showDialog<void>(
      context: context,
      barrierDismissible: barrierDismissible && !required,
      builder: (BuildContext context) => UpdatePrompt(
        key: key,
        required: required,
        releaseNotes: releaseNotes,
        onLater: () {
          onUserLater(context, true);
          PlatformManager.instance.analytics.upgradeModalDismissed();
        },
        onUpdate: () {
          onUserUpdated(context, !required);
          PlatformManager.instance.analytics.upgradeModalClicked();
        },
      ),
    );
  }
}

/// The update pop-up, in Omi's own words rather than the `upgrader` package's ("…is now
/// available-you have…"), in every locale. A version that is no longer supported gets "Update
/// required" and no Not Now. The store's release notes, when there are any, add a short What's New.
class UpdatePrompt extends StatelessWidget {
  const UpdatePrompt({
    super.key,
    required this.required,
    required this.onUpdate,
    required this.onLater,
    this.releaseNotes,
  });

  /// This version is blocked: updating is the only way on.
  final bool required;
  final String? releaseNotes;
  final VoidCallback onUpdate;
  final VoidCallback onLater;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final notes = UpdateWhatsNew.fromReleaseNotes(releaseNotes);
    return OmiAlertDialog(
      title: required ? l10n.updateRequiredTitle : l10n.updateAvailableTitle,
      message: required ? l10n.updateRequiredMessage : l10n.updateAvailableMessage,
      content: notes == null ? null : UpdateWhatsNew(notes: notes),
      actions: [
        if (!required) OmiDialogAction(key: const ValueKey('update_not_now'), label: l10n.notNow, onPressed: onLater),
        OmiDialogAction(key: const ValueKey('update_now'), label: l10n.update, isDefault: true, onPressed: onUpdate),
      ],
    );
  }
}

/// "What's New" in the update pop-up: the first two lines of the store's release notes.
class UpdateWhatsNew extends StatelessWidget {
  const UpdateWhatsNew({super.key, required this.notes});

  final String notes;

  /// The first two non-empty lines of [releaseNotes], list markers dropped; null when there is
  /// nothing to show.
  static String? fromReleaseNotes(String? releaseNotes) {
    final lines = (releaseNotes ?? '')
        .split('\n')
        .map((line) => line.trim().replaceFirst(RegExp(r'^[•\-*–]\s*'), '').trim())
        .where((line) => line.isNotEmpty)
        .take(2)
        .toList();
    return lines.isEmpty ? null : lines.join('\n');
  }

  @override
  Widget build(BuildContext context) {
    final style = DefaultTextStyle.of(context).style;
    return Padding(
      padding: const EdgeInsets.only(top: 12),
      child: Column(
        key: const ValueKey('update_whats_new'),
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(context.l10n.whatsNew, style: style.copyWith(fontWeight: FontWeight.w600)),
          const SizedBox(height: 2),
          Text(notes, maxLines: 4, overflow: TextOverflow.ellipsis),
        ],
      ),
    );
  }
}
