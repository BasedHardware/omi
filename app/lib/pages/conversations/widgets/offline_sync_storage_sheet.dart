import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';

import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Offline Sync storage categories. Counts and clear actions are owned by the page.
///
/// With a [nativeTitle] (a `showOmiSheet` nativeBuilder) the categories are a native list that runs
/// the same clear callbacks; an unsupported host keeps this sheet in its [OmiSheetScaffold].
class OfflineSyncStorageSheet extends StatelessWidget {
  /// The classic sheet's padding, shared by its native fallback.
  static const sheetPadding = EdgeInsets.fromLTRB(OmiSpacing.xl, OmiSpacing.xs, OmiSpacing.xl, OmiSpacing.xl);

  final String? nativeTitle;
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
    this.nativeTitle,
  });

  @override
  Widget build(BuildContext context) {
    final title = nativeTitle;
    if (title != null) {
      final l = context.l10n;
      return IosNativeSurface(
        title: title,
        fallback: OmiSheetScaffold(
          title: title,
          padding: sheetPadding,
          child: OfflineSyncStorageSheet(
            syncedCount: syncedCount,
            pendingCount: pendingCount,
            totalCount: totalCount,
            onClearSynced: onClearSynced,
            onClearPending: onClearPending,
            onClearAll: onClearAll,
          ),
        ),
        toolbar: [
          NativeRow('storage_close', l.close, symbol: 'xmark', action: (_) => Navigator.of(context).maybePop()),
        ],
        sections: [
          NativeSection('storage_categories', [
            NativeRow('storage_synced', l.synced, kind: 'label', subtitle: '${l.safelyBackedUp} · $syncedCount'),
            NativeRow('storage_clear_synced', l.clear, enabled: syncedCount > 0, action: (_) => onClearSynced()),
            NativeRow('storage_pending', l.pending, kind: 'label', subtitle: '${l.notYetSynced} · $pendingCount'),
            NativeRow('storage_clear_pending', l.clear, enabled: pendingCount > 0, action: (_) => onClearPending()),
          ]),
          if (totalCount > 0)
            NativeSection('storage_clear', [
              NativeRow('storage_clear_all', l.clearAll, destructive: true, action: (_) => onClearAll()),
            ]),
        ],
      );
    }
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Synced row
          _StorageRow(
            icon: FontAwesomeIcons.circleCheck,
            iconColor: Colors.green,
            title: context.l10n.synced,
            subtitle: context.l10n.safelyBackedUp,
            count: syncedCount,
            onClear: syncedCount > 0 ? onClearSynced : null,
            clearLabel: context.l10n.clear,
          ),
          const SizedBox(height: 12),
          // Pending row
          _StorageRow(
            icon: FontAwesomeIcons.clockRotateLeft,
            iconColor: Colors.orange,
            title: context.l10n.pending,
            subtitle: context.l10n.notYetSynced,
            count: pendingCount,
            onClear: pendingCount > 0 ? onClearPending : null,
            clearLabel: context.l10n.clear,
          ),
          if (totalCount > 0) ...[
            const SizedBox(height: 20),
            OmiButton.destructive(label: context.l10n.clearAll, expand: true, onPressed: onClearAll),
          ],
        ],
      ),
    );
  }
}

class _StorageRow extends StatelessWidget {
  final FaIconData icon;
  final Color iconColor;
  final String title;
  final String subtitle;
  final int count;
  final VoidCallback? onClear;
  final String clearLabel;

  const _StorageRow({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.subtitle,
    required this.count,
    required this.onClear,
    required this.clearLabel,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
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
            Container(
              width: 36,
              height: 36,
              decoration: BoxDecoration(
                color: iconColor.withValues(alpha: 0.15),
                borderRadius: OmiRadius.mdAll,
              ),
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
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500),
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
                          '$count',
                          style: OmiType.caption.copyWith(color: OmiColors.textPrimary.withValues(alpha: 0.7)),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 3),
                  Text(subtitle, style: OmiType.caption.copyWith(color: OmiColors.textPrimary.withValues(alpha: 0.7))),
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
