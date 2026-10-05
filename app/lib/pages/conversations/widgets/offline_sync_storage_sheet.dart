import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Offline Sync storage categories. Counts and clear actions are owned by the page.
class OfflineSyncStorageSheet extends StatelessWidget {
  final int syncedCount;
  final int pendingCount;
  final int totalCount;
  final VoidCallback onClearSynced;
  final VoidCallback onClearPending;
  final VoidCallback onClearAll;

  const OfflineSyncStorageSheet({
    super.key,
    required this.syncedCount,
    required this.pendingCount,
    required this.totalCount,
    required this.onClearSynced,
    required this.onClearPending,
    required this.onClearAll,
  });

  @override
  Widget build(BuildContext context) {
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Synced row
          _StorageRow(
            icon: FontAwesomeIcons.circleCheck,
            title: context.l10n.synced,
            subtitle: context.l10n.safelyBackedUp,
            count: syncedCount,
            onClear: syncedCount > 0 ? onClearSynced : null,
            clearLabel: context.l10n.clear,
          ),
          const SizedBox(height: OmiSpacing.sm),
          // Pending row
          _StorageRow(
            icon: FontAwesomeIcons.clockRotateLeft,
            title: context.l10n.pending,
            subtitle: context.l10n.notYetSynced,
            count: pendingCount,
            onClear: pendingCount > 0 ? onClearPending : null,
            clearLabel: context.l10n.clear,
          ),
          if (totalCount > 0) ...[
            const SizedBox(height: OmiSpacing.lg),
            OmiButton.destructive(label: context.l10n.clearAll, expand: true, onPressed: onClearAll),
          ],
        ],
      ),
    );
  }
}

class _StorageRow extends StatelessWidget {
  /// Ink at 70%: quieter than the title, still 4.5:1 on the card in light and dark.
  static Color get _muted => OmiColors.textPrimary.withValues(alpha: 0.7);

  final FaIconData icon;
  final String title;
  final String subtitle;
  final int count;
  final VoidCallback? onClear;
  final String clearLabel;

  const _StorageRow({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.count,
    required this.onClear,
    required this.clearLabel,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.lgAll),
      child: LayoutBuilder(builder: (context, constraints) {
        final actionBelow = constraints.maxWidth < 280 || MediaQuery.textScalerOf(context).scale(1) > 1.3;
        final clear = OmiButton.secondary(
          label: clearLabel,
          size: OmiButtonSize.compact,
          onPressed: onClear,
        );
        return Column(mainAxisSize: MainAxisSize.min, children: [
          Row(children: [
            // Black and white like the rest of Settings: the icon in its tile, no status colours.
            OmiSettingsIconTile(FaIcon(icon)),
            const SizedBox(width: OmiSpacing.md),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Flexible(
                        child: Text(
                          title,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: OmiType.body.copyWith(fontWeight: FontWeight.w500),
                        ),
                      ),
                      const SizedBox(width: OmiSpacing.xs),
                      Text('$count', style: OmiType.subhead.copyWith(color: _muted)),
                    ],
                  ),
                  const SizedBox(height: 2),
                  Text(subtitle, style: OmiType.footnote.copyWith(color: _muted)),
                ],
              ),
            ),
            if (onClear != null && !actionBelow) clear,
          ]),
          if (onClear != null && actionBelow)
            Padding(
              padding: const EdgeInsets.only(top: OmiSpacing.xs),
              child: Align(alignment: AlignmentDirectional.centerEnd, child: clear),
            ),
        ]);
      }),
    );
  }
}
