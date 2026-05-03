import 'package:flutter/material.dart';

import 'package:nooto_v2/theme/app_theme.dart';
import '../models/followups_data.dart';

/// Widget for rendering journalist follow-up tasks from LLM-generated data.
class FollowupsWidget extends StatefulWidget {
  final FollowupsDisplayData data;
  static const int _initialVisibleCount = 3;

  const FollowupsWidget({super.key, required this.data});

  @override
  State<FollowupsWidget> createState() => _FollowupsWidgetState();
}

class _FollowupsWidgetState extends State<FollowupsWidget> {
  bool _isExpanded = false;

  void _toggleExpanded() {
    setState(() {
      _isExpanded = !_isExpanded;
    });
  }

  Widget _buildToggleButton() {
    return GestureDetector(
      onTap: _toggleExpanded,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingL, vertical: 10),
        decoration: BoxDecoration(
          color: AppColors.backgroundTertiary,
          borderRadius: BorderRadius.circular(AppStyles.radiusXLarge),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(_isExpanded ? Icons.expand_less : Icons.expand_more, size: 18, color: AppColors.textTertiary),
            const SizedBox(width: 6),
            Text(
              _isExpanded
                  ? 'Show less'
                  : 'Show ${widget.data.items.length - FollowupsWidget._initialVisibleCount} more',
              style: const TextStyle(color: AppColors.textTertiary, fontSize: 13, fontWeight: FontWeight.w500),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (widget.data.isEmpty) {
      return const SizedBox.shrink();
    }

    final hasMore = widget.data.items.length > FollowupsWidget._initialVisibleCount;
    final visibleItems = _isExpanded || !hasMore
        ? widget.data.items
        : widget.data.items.take(FollowupsWidget._initialVisibleCount).toList();

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppStyles.spacingM),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Padding(
            padding: const EdgeInsets.only(bottom: AppStyles.spacingM),
            child: Row(
              children: const [
                Icon(Icons.checklist_rounded, color: AppColors.textTertiary, size: 18),
                SizedBox(width: AppStyles.spacingS),
                Text(
                  'Follow-ups & Fact-checks',
                  style: TextStyle(color: AppColors.textPrimary, fontSize: 16, fontWeight: FontWeight.w600),
                ),
              ],
            ),
          ),
          Column(
            children: visibleItems.asMap().entries.map((entry) {
              final index = entry.key;
              final item = entry.value;
              final isLastVisible = index == visibleItems.length - 1;
              final isActualLast = index == widget.data.items.length - 1;
              return _FollowupItem(item: item, isLast: _isExpanded ? isActualLast : isLastVisible);
            }).toList(),
          ),
          if (hasMore)
            Padding(
              padding: const EdgeInsets.only(top: AppStyles.spacingM),
              child: Center(child: _buildToggleButton()),
            ),
        ],
      ),
    );
  }
}

class _FollowupItem extends StatelessWidget {
  final FollowupItemData item;
  final bool isLast;

  const _FollowupItem({required this.item, required this.isLast});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: isLast ? 0 : AppStyles.spacingM),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(color: item.type.color, shape: BoxShape.circle),
            ),
          ),
          const SizedBox(width: AppStyles.spacingM),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingS, vertical: 3),
                  decoration: BoxDecoration(color: item.type.backgroundColor, borderRadius: BorderRadius.circular(4)),
                  child: Text(
                    item.type.displayName,
                    style: TextStyle(color: item.type.color, fontSize: 12, fontWeight: FontWeight.w600),
                  ),
                ),
                const SizedBox(height: 6),
                Text(item.content, style: const TextStyle(color: AppColors.textSecondary, fontSize: 15, height: 1.5)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
