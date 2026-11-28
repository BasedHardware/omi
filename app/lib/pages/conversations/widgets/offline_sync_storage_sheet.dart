import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/services/wals/storage_clear.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Manage Storage: how much audio the phone and the pendant hold, by whether it
/// can be removed safely. Amounts are hours of audio, never file counts: each
/// file is about a minute, so a count of 26,589 read as conversations.
class OfflineSyncStorageSheet extends StatelessWidget {
  final StorageAmounts amounts;
  final VoidCallback onFreeUpSpace;
  final VoidCallback onDeletePending;
  final VoidCallback onDeleteAll;

  /// Extra settings shown between the rows and Delete everything (Auto-Remove).
  final Widget? footer;

  const OfflineSyncStorageSheet({
    super.key,
    required this.amounts,
    required this.onFreeUpSpace,
    required this.onDeletePending,
    required this.onDeleteAll,
    this.footer,
  });

  @override
  Widget build(BuildContext context) {
    final l = context.l10n;
    final pendingLines = [
      storageWhereLine(amounts, l),
      l.storageNotUploadedWarning,
    ];
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _StorageRow(
            icon: FontAwesomeIcons.circleCheck,
            iconColor: Colors.green,
            title: l.storageUploadedTitle,
            amount: OmiDuration.compact(amounts.uploadedSeconds, l),
            lines: [l.storageUploadedSubtitle],
            action: amounts.uploadedCount > 0
                ? OmiButton.secondary(
                    label: l.storageFreeUpSpace, size: OmiButtonSize.compact, onPressed: onFreeUpSpace)
                : null,
          ),
          const SizedBox(height: 12),
          _StorageRow(
            icon: FontAwesomeIcons.clockRotateLeft,
            iconColor: Colors.orange,
            title: l.storageNotUploadedTitle,
            amount: OmiDuration.compact(amounts.pendingSeconds, l),
            lines: amounts.pendingCount > 0 ? pendingLines : const [],
            action: amounts.pendingCount > 0
                ? OmiButton.destructive(label: l.delete, size: OmiButtonSize.compact, onPressed: onDeletePending)
                : null,
          ),
          if (footer != null) ...[const SizedBox(height: 12), footer!],
          if (amounts.allCount > 0) ...[
            const SizedBox(height: 20),
            OmiButton.destructive(label: l.storageDeleteEverything, expand: true, onPressed: onDeleteAll),
          ],
        ],
      ),
    );
  }
}

/// Where audio that has not been uploaded is waiting.
String storageWhereLine(StorageAmounts amounts, AppLocalizations l) {
  if (amounts.devicePendingSeconds <= 0) return l.storageOnThisPhone;
  if (amounts.phonePendingSeconds <= 0) return l.storageOnYourOmi;
  return l.storageOnPhoneAndOmi(
    OmiDuration.compact(amounts.phonePendingSeconds, l),
    OmiDuration.compact(amounts.devicePendingSeconds, l),
  );
}

class _StorageRow extends StatelessWidget {
  final FaIconData icon;
  final Color iconColor;
  final String title;
  final String amount;
  final List<String> lines;
  final Widget? action;

  const _StorageRow({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.amount,
    required this.lines,
    required this.action,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.lgAll),
      child: LayoutBuilder(builder: (context, constraints) {
        // On a phone the row is ~345 pt wide; beside the text a label like
        // "Free up space" would squeeze the title onto two lines.
        final actionBelow = constraints.maxWidth < 400 || MediaQuery.textScalerOf(context).scale(1) > 1.3;
        return Column(mainAxisSize: MainAxisSize.min, children: [
          Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(color: iconColor.withValues(alpha: 0.15), borderRadius: OmiRadius.mdAll),
              child: Center(child: FaIcon(icon, size: 16, color: iconColor)),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Flexible(
                        child: Text(
                          title,
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                          style: OmiType.subhead.copyWith(color: OmiColors.textPrimary, fontWeight: FontWeight.w500),
                        ),
                      ),
                      const SizedBox(width: 8),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                        decoration: BoxDecoration(
                          color: OmiColors.textPrimary.withValues(alpha: 0.08),
                          borderRadius: OmiRadius.smAll,
                        ),
                        child: Text(
                          amount,
                          style: OmiType.caption.copyWith(color: OmiColors.textPrimary.withValues(alpha: 0.7)),
                        ),
                      ),
                    ],
                  ),
                  for (final line in lines) ...[
                    const SizedBox(height: 3),
                    Text(line, style: OmiType.caption.copyWith(color: OmiColors.textPrimary.withValues(alpha: 0.7))),
                  ],
                ],
              ),
            ),
            if (action != null && !actionBelow) ...[const SizedBox(width: 8), action!],
          ]),
          if (action != null && actionBelow)
            Padding(
              padding: const EdgeInsets.only(top: OmiSpacing.xs),
              child: Align(alignment: AlignmentDirectional.centerEnd, child: action),
            ),
        ]);
      }),
    );
  }
}
