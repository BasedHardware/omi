import 'package:flutter/material.dart';

import 'package:nooto_v2/theme/app_theme.dart';
import '../models/timeline_data.dart';

/// Widget for rendering a chronological story timeline from LLM-generated data.
class TimelineWidget extends StatefulWidget {
  final TimelineDisplayData data;
  static const int _initialVisibleCount = 5;

  const TimelineWidget({super.key, required this.data});

  @override
  State<TimelineWidget> createState() => _TimelineWidgetState();
}

class _TimelineWidgetState extends State<TimelineWidget> {
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
                  : 'Show ${widget.data.events.length - TimelineWidget._initialVisibleCount} more events',
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

    final hasMore = widget.data.events.length > TimelineWidget._initialVisibleCount;
    final visibleEvents = _isExpanded || !hasMore
        ? widget.data.events
        : widget.data.events.take(TimelineWidget._initialVisibleCount).toList();

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppStyles.spacingM),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          if (widget.data.title != null && widget.data.title!.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: AppStyles.spacingM),
              child: Text(
                widget.data.title!,
                style: const TextStyle(color: AppColors.textPrimary, fontSize: 16, fontWeight: FontWeight.w600),
              ),
            ),
          Column(
            children: visibleEvents.asMap().entries.map((entry) {
              final index = entry.key;
              final event = entry.value;
              final isLastVisible = index == visibleEvents.length - 1;
              final isActualLast = index == widget.data.events.length - 1;
              return _TimelineEventItem(event: event, isLast: _isExpanded ? isActualLast : isLastVisible);
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

class _TimelineEventItem extends StatelessWidget {
  final TimelineEventData event;
  final bool isLast;

  const _TimelineEventItem({required this.event, required this.isLast});

  @override
  Widget build(BuildContext context) {
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 24,
            child: Column(
              children: [
                const SizedBox(height: 6),
                Container(
                  width: 10,
                  height: 10,
                  decoration: BoxDecoration(color: event.labelType.color, shape: BoxShape.circle),
                ),
                if (!isLast) Expanded(child: Container(width: 2, color: Colors.white.withValues(alpha: 0.2))),
              ],
            ),
          ),
          const SizedBox(width: AppStyles.spacingM),
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: isLast ? 0 : AppStyles.spacingL),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      if (event.time.isNotEmpty)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: AppColors.backgroundTertiary,
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            event.time,
                            style: const TextStyle(
                              color: AppColors.textTertiary,
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              fontFeatures: [FontFeature.tabularFigures()],
                            ),
                          ),
                        ),
                      if (event.time.isNotEmpty) const SizedBox(width: AppStyles.spacingS),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: AppStyles.spacingS, vertical: 3),
                        decoration: BoxDecoration(
                          color: event.labelType.color.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          event.label,
                          style: TextStyle(color: event.labelType.color, fontSize: 12, fontWeight: FontWeight.w600),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    event.description,
                    style: const TextStyle(color: AppColors.textSecondary, fontSize: 15, height: 1.5),
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }
}
