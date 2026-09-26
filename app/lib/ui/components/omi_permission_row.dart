import 'dart:async';

import 'package:flutter/material.dart';

import 'package:permission_handler/permission_handler.dart';

import 'package:omi/ui/components/omi_balanced_text.dart';
import 'package:omi/ui/components/omi_button.dart';
import 'package:omi/ui/omi_tokens.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Where one permission stands, as the reader can act on it (docs/ux-contract.md §15).
enum OmiPermissionStatus {
  /// Not granted, and asking again shows the system prompt. Also the state before the first ask:
  /// iOS reports "not determined" as denied.
  askable,

  /// Granted (including limited / provisional grants).
  granted,

  /// The system will not prompt again: permanently denied or restricted. Only Settings can fix it.
  blocked,

  /// The permission is fine but the service behind it is switched off (Location Services).
  serviceOff;

  /// Maps a `permission_handler` status. `denied` stays [askable] because both platforms prompt
  /// again after a plain denial; they report `permanentlyDenied` once they stop prompting.
  static OmiPermissionStatus fromStatus(PermissionStatus status) => switch (status) {
        PermissionStatus.granted || PermissionStatus.limited || PermissionStatus.provisional => granted,
        PermissionStatus.permanentlyDenied || PermissionStatus.restricted => blocked,
        PermissionStatus.denied => askable,
      };
}

/// One permission as a pre-prompt: what it is, why Omi wants it, and one action that fits its state.
///
/// * [OmiPermissionStatus.askable] → **Allow**, which runs [onAllow] (the caller fires the system
///   prompt there and then reports the new status).
/// * [OmiPermissionStatus.granted] → a check and "Allowed"; nothing to press.
/// * [OmiPermissionStatus.blocked] / [OmiPermissionStatus.serviceOff] → a line saying so and
///   **Open Settings** ([onOpenSettings], default `openAppSettings`).
///
/// The row never prompts by itself, and a screen's Continue never prompts either: only Allow does.
/// Onboarding and the Settings permission list use the same row so the copy and the recovery
/// path cannot drift.
///
/// ```dart
/// OmiPermissionRow(
///   icon: Icons.notifications_none,
///   title: l10n.notifications,
///   reason: l10n.notificationsDesc,
///   status: _notifications,
///   onAllow: _requestNotifications,
/// )
/// ```
class OmiPermissionRow extends StatelessWidget {
  const OmiPermissionRow({
    super.key,
    required this.title,
    required this.reason,
    required this.status,
    required this.onAllow,
    this.icon,
    this.leading,
    this.onOpenSettings,
    this.serviceOffMessage,
    this.inGroup = false,
  });

  /// v2: the row sits in a shared grouped card (the caller draws the card and the hairlines), with
  /// its icon in a 30pt tile; otherwise it is its own card.
  final bool inGroup;

  final String title;

  /// One sentence saying what Omi does with the permission.
  final String reason;
  final OmiPermissionStatus status;

  /// Fires the system prompt. May return a [Future]; the Allow button spins until it completes.
  final FutureOr<void> Function() onAllow;

  final IconData? icon;

  /// A leading glyph that is not a Material [IconData] — for example `FaIcon(FontAwesomeIcons.solidBell)`
  /// so the row matches the Settings permission list. Sized and coloured like [icon]; wins over it.
  final Widget? leading;

  /// Defaults to `openAppSettings()`.
  final FutureOr<void> Function()? onOpenSettings;

  /// Shown for [OmiPermissionStatus.serviceOff]; defaults to the Location Services line.
  final String? serviceOffMessage;

  Future<void> _openSettings() async {
    final open = onOpenSettings;
    if (open != null) {
      await open();
      return;
    }
    await openAppSettings();
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final String? statusLine = switch (status) {
      OmiPermissionStatus.blocked => l10n.permissionBlockedHint,
      OmiPermissionStatus.serviceOff => serviceOffMessage ?? l10n.locationServiceDisabledDesc,
      _ => null,
    };

    final Widget trailing = switch (status) {
      OmiPermissionStatus.granted => Semantics(
          label: l10n.permissionAllowed,
          child: ExcludeSemantics(
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Icon(Icons.check_circle, color: OmiColors.success, size: 20),
                const SizedBox(width: OmiSpacing.xxs),
                Text(l10n.permissionAllowed, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
              ],
            ),
          ),
        ),
      // v2: a quiet capsule; the system prompt is the real decision.
      OmiPermissionStatus.askable => OmiButton.secondary(
          key: const Key('omi_permission_allow'),
          label: l10n.allow,
          onPressed: onAllow,
          size: OmiButtonSize.compact,
        ),
      OmiPermissionStatus.blocked || OmiPermissionStatus.serviceOff => OmiButton.secondary(
          key: const Key('omi_permission_open_settings'),
          label: l10n.openSettings,
          onPressed: _openSettings,
          size: OmiButtonSize.compact,
        ),
    };

    return Container(
      constraints: const BoxConstraints(minHeight: 64),
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
      decoration: inGroup
          ? null
          : BoxDecoration(
              color: OmiColors.surface1,
              borderRadius: OmiRadius.rowAll,
              border: Border.all(color: OmiColors.border),
            ),
      child: Row(
        children: [
          if (leading != null || icon != null) ...[
            ExcludeSemantics(
              child: IconTheme.merge(
                data: IconThemeData(color: OmiColors.textPrimary, size: 15),
                child: Container(
                  width: 30,
                  height: 30,
                  alignment: Alignment.center,
                  decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.smAll),
                  child: leading ?? Icon(icon),
                ),
              ),
            ),
            const SizedBox(width: OmiSpacing.sm),
          ],
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(title, style: OmiType.headline),
                const SizedBox(height: 2),
                OmiBalancedText(reason, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                if (statusLine != null) ...[
                  const SizedBox(height: OmiSpacing.xxs),
                  OmiBalancedText(statusLine, style: OmiType.footnote.copyWith(color: OmiColors.warning)),
                ],
              ],
            ),
          ),
          const SizedBox(width: OmiSpacing.sm),
          trailing,
        ],
      ),
    );
  }
}
