import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import 'package:nooto_v2/library/memory_model.dart';
import 'package:nooto_v2/theme/app_theme.dart';

final _pickedUpFormat = DateFormat.MMMd();

/// Single memory row in the Library screen.
///
/// Visual grammar (per /plan-design-review):
///   ┌─────────────────────────────────────────────┐
///   │ INFERRED                                    │  ← eyebrow when manually_added=false
///   │ The actual memory content text wraps to up  │
///   │ to 3 lines and ellipses if longer…  🔒  ›  │  ← lock if locked, chevron rotates on expand
///   ├─────────────────────────────────────────────┤  (only when expanded:)
///   │ Picked up Apr 14   View conversation →      │
///   │                                    Delete   │
///   └─────────────────────────────────────────────┘
class MemoryRow extends StatefulWidget {
  const MemoryRow({
    super.key,
    required this.item,
    required this.onDelete,
    required this.onViewConversation,
  });

  final MemoryItem item;

  /// Confirms-and-deletes. Caller hooks up provider.delete(id).
  final Future<void> Function() onDelete;

  /// Stub in v0 — caller can show a toast or open a future Chat-detail route.
  final VoidCallback onViewConversation;

  @override
  State<MemoryRow> createState() => _MemoryRowState();
}

class _MemoryRowState extends State<MemoryRow> {
  bool _expanded = false;

  void _toggle() => setState(() => _expanded = !_expanded);

  Future<void> _confirmDelete() async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppColors.backgroundSecondary,
        title: const Text(
          'Delete this memory?',
          style: TextStyle(color: AppColors.textPrimary),
        ),
        content: const Text(
          "Nooto won't recall this when answering you. You can't undo this.",
          style: TextStyle(color: AppColors.textTertiary),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text(
              'Delete',
              style: TextStyle(color: AppColors.errorColor),
            ),
          ),
        ],
      ),
    );
    if (!mounted || ok != true) return;
    await widget.onDelete();
  }

  @override
  Widget build(BuildContext context) {
    final item = widget.item;
    final inferred = !item.manuallyAdded;
    return Semantics(
      button: true,
      label: _semanticsLabel(item, _expanded),
      child: DecoratedBox(
        decoration: BoxDecoration(
          border: Border(
            bottom: BorderSide(
              color: Colors.white.withValues(alpha: 0.06),
              width: 0.5,
            ),
          ),
        ),
        child: InkWell(
          onTap: _toggle,
          borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
          child: Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: AppStyles.spacingS,
              vertical: AppStyles.spacingM,
            ),
            child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (inferred) const _InferredEyebrow(),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Expanded(
                    child: Text(
                      item.content,
                      maxLines: _expanded ? null : 3,
                      overflow: _expanded ? null : TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontSize: 15,
                        color: AppColors.textPrimary,
                        height: 1.4,
                      ),
                    ),
                  ),
                  const SizedBox(width: AppStyles.spacingS),
                  if (item.isLocked) ...[
                    const Padding(
                      padding: EdgeInsets.only(top: 2),
                      child: Icon(
                        Icons.lock_outline_rounded,
                        size: 14,
                        color: AppColors.textTertiary,
                      ),
                    ),
                    const SizedBox(width: 4),
                  ],
                  Padding(
                    padding: const EdgeInsets.only(top: 1),
                    child: AnimatedRotation(
                      turns: _expanded ? 0.25 : 0,
                      duration: const Duration(milliseconds: 180),
                      child: const Icon(
                        Icons.chevron_right_rounded,
                        size: 20,
                        color: AppColors.textTertiary,
                      ),
                    ),
                  ),
                ],
              ),
              AnimatedSize(
                duration: const Duration(milliseconds: 180),
                curve: Curves.easeOut,
                alignment: Alignment.topCenter,
                child: _expanded
                    ? Padding(
                        padding: const EdgeInsets.only(top: AppStyles.spacingS),
                        child: _ExpandedDetail(
                          item: item,
                          onViewConversation: widget.onViewConversation,
                          onDelete: _confirmDelete,
                        ),
                      )
                    : const SizedBox.shrink(),
              ),
            ],
          ),
          ),
        ),
      ),
    );
  }

  static String _semanticsLabel(MemoryItem item, bool expanded) {
    final inferred = item.manuallyAdded ? '' : 'Inferred. ';
    final locked = item.isLocked ? 'Locked. ' : '';
    final action = expanded ? 'Double-tap to collapse.' : 'Double-tap to expand.';
    return 'Memory: ${item.content}. Category: ${item.bucket.label}. $inferred$locked$action';
  }
}

class _InferredEyebrow extends StatelessWidget {
  const _InferredEyebrow();

  @override
  Widget build(BuildContext context) {
    return const Padding(
      padding: EdgeInsets.only(bottom: 4),
      child: Text(
        'INFERRED',
        style: TextStyle(
          fontSize: 11,
          fontWeight: FontWeight.w600,
          color: AppColors.textTertiary,
          letterSpacing: 0.6,
        ),
      ),
    );
  }
}

class _ExpandedDetail extends StatelessWidget {
  const _ExpandedDetail({
    required this.item,
    required this.onViewConversation,
    required this.onDelete,
  });

  final MemoryItem item;
  final VoidCallback onViewConversation;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    final ts = item.createdAt ?? item.updatedAt;
    final pickedUp = ts != null ? 'Picked up ${_pickedUpFormat.format(ts)}' : null;
    final hasConversation = item.conversationId != null;
    final hasMeta = pickedUp != null || hasConversation;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (hasMeta)
          Row(
            children: [
              if (pickedUp != null)
                Text(
                  pickedUp,
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppColors.textTertiary,
                  ),
                ),
              if (pickedUp != null && hasConversation)
                const SizedBox(width: AppStyles.spacingM),
              if (hasConversation)
                GestureDetector(
                  onTap: onViewConversation,
                  child: const Text(
                    'View conversation →',
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w500,
                      color: AppColors.brandPrimary,
                    ),
                  ),
                ),
            ],
          ),
        Align(
          alignment: Alignment.centerRight,
          child: TextButton(
            onPressed: onDelete,
            style: TextButton.styleFrom(
              padding: const EdgeInsets.symmetric(
                horizontal: AppStyles.spacingS,
                vertical: AppStyles.spacingXS,
              ),
              minimumSize: Size.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: const Text(
              'Delete',
              style: TextStyle(
                fontSize: 14,
                fontWeight: FontWeight.w500,
                color: AppColors.errorColor,
              ),
            ),
          ),
        ),
      ],
    );
  }
}
