import 'package:flutter/material.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Memories without supported relationships are readable source records,
/// never fabricated entity nodes or edges in the Mind Map.
class MemoryGraphCatalog extends StatelessWidget {
  const MemoryGraphCatalog({super.key, required this.records, this.compact = false, this.loadMore});

  final List<dynamic> records;
  final bool compact;
  final Widget? loadMore;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: ListView(
        key: const ValueKey('mind_map_memory_catalog'),
        padding: const EdgeInsets.all(OmiSpacing.md),
        children: [
          Text(context.l10n.memories, style: OmiType.title3),
          const SizedBox(height: OmiSpacing.sm),
          for (final record in (compact ? records.take(1) : records))
            Padding(
              padding: const EdgeInsets.symmetric(vertical: OmiSpacing.sm),
              child: Text(
                record['label'] as String? ?? '',
                maxLines: compact ? 2 : null,
                overflow: compact ? TextOverflow.ellipsis : null,
                style: OmiType.body.copyWith(color: OmiColors.textSecondary),
              ),
            ),
          if (!compact && loadMore != null) loadMore!,
        ],
      ),
    );
  }
}
