import 'package:flutter/material.dart';

import 'package:omi/ui/ui.dart';

/// The small label over a run of recordings on the sync pages (a day, a day and hour, or a
/// source), like every section label in Settings, with an optional count.
class SyncListHeader extends StatelessWidget {
  const SyncListHeader({super.key, required this.label, this.count, this.first = false});

  final String label;
  final int? count;

  /// The first header sits right under the filter; later ones leave a section gap.
  final bool first;

  // The list's gutter plus a label's own inset: the same line as the Storage and Recordings
  // labels above, and the row content below.
  static const _inset = OmiSpacing.md + OmiSpacing.md;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.fromLTRB(_inset, first ? 0 : OmiSpacing.xl, _inset, OmiSpacing.xs),
      child: Row(
        children: [
          Flexible(
            child: Semantics(
              header: true,
              child: Text(
                label,
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
                style: OmiType.subhead.copyWith(fontWeight: FontWeight.w500, color: OmiColors.textSecondary),
              ),
            ),
          ),
          if (count != null) ...[
            const SizedBox(width: OmiSpacing.xs),
            Text('$count', style: OmiType.subhead.copyWith(color: OmiColors.textTertiary)),
          ],
        ],
      ),
    );
  }
}
