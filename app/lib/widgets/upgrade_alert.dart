// Copyright (c) 2023 Larry Aasen. All rights reserved.

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';

import 'package:upgrader/upgrader.dart';

import 'package:omi/gen/assets.gen.dart';
import 'package:omi/ui/ui.dart';
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
      show: (promptContext) => showUpdatePrompt(
        promptContext,
        key: key,
        required: widget.upgrader.blocked(),
        releaseNotes: releaseNotes,
        // The sheet closes itself, so neither answer asks the upgrader to pop anything.
        onLater: () {
          onUserLater(promptContext, false);
          PlatformManager.instance.analytics.upgradeModalDismissed();
        },
        onUpdate: () {
          onUserUpdated(promptContext, false);
          PlatformManager.instance.analytics.upgradeModalClicked();
        },
      ),
    );
  }
}

/// Shows the update prompt as an Omi sheet and reports the answer: [onUpdate] for Update, [onLater]
/// for Not Now, a swipe down or a tap outside.
///
/// A [required] update has no Not Now and no drag handle, and nothing dismisses it (swipe, scrim,
/// back); Update reports and leaves the sheet up until the new version takes over.
Future<void> showUpdatePrompt(
  BuildContext context, {
  Key? key,
  required bool required,
  String? releaseNotes,
  required VoidCallback onUpdate,
  required VoidCallback onLater,
}) async {
  final updated = await showOmiSurfaceSheet<bool>(
    context: context,
    isDismissible: !required,
    enableDrag: !required,
    showDragHandle: !required,
    builder: (sheetContext) => PopScope(
      canPop: !required,
      child: OmiSheetScaffold(
        showCloseButton: false,
        padding: EdgeInsets.fromLTRB(OmiSpacing.xl, required ? OmiSpacing.xl : 0, OmiSpacing.xl, OmiSpacing.xs),
        child: UpdatePrompt(
          key: key,
          required: required,
          releaseNotes: releaseNotes,
          onUpdate: required ? onUpdate : () => Navigator.of(sheetContext).pop(true),
          onLater: () => Navigator.of(sheetContext).pop(false),
        ),
      ),
    ),
  );
  if (required) return;
  updated == true ? onUpdate() : onLater();
}

/// The update sheet's content, in Omi's own words rather than the `upgrader` package's ("…is now
/// available-you have…"), in every locale: the app icon, the title and message, a short What's New
/// from the store's release notes when there are any, then Update and Not Now. A version that is
/// no longer supported gets "Update required" and no Not Now.
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
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Center(child: _OmiAppIcon()),
          const SizedBox(height: OmiSpacing.md),
          Semantics(
            header: true,
            child: Text(
              required ? l10n.updateRequiredTitle : l10n.updateAvailableTitle,
              style: OmiType.title3,
              textAlign: TextAlign.center,
            ),
          ),
          const SizedBox(height: OmiSpacing.xs),
          Text(
            required ? l10n.updateRequiredMessage : l10n.updateAvailableMessage,
            // textTertiary, not textSecondary: it stays at 4.5:1 or better in light mode too.
            style: OmiType.subhead.copyWith(color: OmiColors.textTertiary, height: 1.4),
            textAlign: TextAlign.center,
          ),
          if (notes != null) ...[
            const SizedBox(height: OmiSpacing.lg),
            UpdateWhatsNew(notes: notes),
          ],
          const SizedBox(height: OmiSpacing.xl),
          OmiButton(key: const ValueKey('update_now'), label: l10n.update, onPressed: onUpdate, expand: true),
          if (!required) ...[
            const SizedBox(height: OmiSpacing.xxs),
            OmiButton.tertiary(
              key: const ValueKey('update_not_now'),
              label: l10n.notNow,
              onPressed: onLater,
              expand: true,
            ),
          ],
        ],
      ),
    );
  }
}

/// Omi's app icon: the eight dots in black on a white tile, and in dark mode the way iOS draws a
/// dark icon, white dots on a dark tile, so it doesn't glare out of the sheet.
class _OmiAppIcon extends StatelessWidget {
  const _OmiAppIcon();

  static const double _size = 64;

  @override
  Widget build(BuildContext context) {
    final light = OmiColors.active == OmiPalette.light;
    return ExcludeSemantics(
      child: Container(
        width: _size,
        height: _size,
        padding: const EdgeInsets.all(OmiSpacing.xs),
        decoration: BoxDecoration(
          color: light ? Colors.white : OmiColors.surface2,
          borderRadius: OmiRadius.lgAll,
          border: Border.all(color: OmiColors.textPrimary.withValues(alpha: light ? 0.1 : 0.08), width: 0.5),
        ),
        child: Assets.images.splashIcon.image(color: OmiColors.textPrimary, colorBlendMode: BlendMode.srcIn),
      ),
    );
  }
}

/// "What's New" in the update sheet: the first two lines of the store's release notes, one bullet
/// each, in a quiet box.
class UpdateWhatsNew extends StatelessWidget {
  const UpdateWhatsNew({super.key, required this.notes});

  /// One note per line.
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
    return Container(
      key: const ValueKey('update_whats_new'),
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
      // A step away from the sheet: the grouped grey in light mode, a raised grey in dark mode
      // (surface0 there is black, a hole in the sheet).
      decoration: BoxDecoration(
        color: OmiColors.active == OmiPalette.light ? OmiColors.surface0 : OmiColors.surface2,
        borderRadius: OmiRadius.mdAll,
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            context.l10n.whatsNew,
            style: OmiType.footnote.copyWith(fontWeight: FontWeight.w600, color: OmiColors.textTertiary),
          ),
          for (final line in notes.split('\n'))
            Padding(
              padding: const EdgeInsets.only(top: OmiSpacing.xxs),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  ExcludeSemantics(child: Text('•', style: OmiType.subhead)),
                  const SizedBox(width: OmiSpacing.xs),
                  Expanded(child: Text(line, style: OmiType.subhead)),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
