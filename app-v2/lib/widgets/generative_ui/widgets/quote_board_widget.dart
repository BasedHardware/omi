import 'package:flutter/material.dart';

import 'package:nooto_v2/theme/app_theme.dart';
import '../models/quote_board_data.dart';

/// Widget for rendering a board of journalist quotes.
class QuoteBoardWidget extends StatefulWidget {
  final QuoteBoardDisplayData data;
  static const int _initialVisibleCount = 3;

  const QuoteBoardWidget({super.key, required this.data});

  @override
  State<QuoteBoardWidget> createState() => _QuoteBoardWidgetState();
}

class _QuoteBoardWidgetState extends State<QuoteBoardWidget> {
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
                  : 'Show ${widget.data.quotes.length - QuoteBoardWidget._initialVisibleCount} more',
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

    final hasMore = widget.data.quotes.length > QuoteBoardWidget._initialVisibleCount;
    final visibleQuotes = _isExpanded || !hasMore
        ? widget.data.quotes
        : widget.data.quotes.take(QuoteBoardWidget._initialVisibleCount).toList();

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: AppStyles.spacingM),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          const Padding(
            padding: EdgeInsets.only(bottom: AppStyles.spacingM),
            child: Text(
              'Quote Board',
              style: TextStyle(color: AppColors.textPrimary, fontSize: 16, fontWeight: FontWeight.w600),
            ),
          ),
          Column(children: visibleQuotes.map((q) => _QuoteBubble(quote: q)).toList()),
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

class _QuoteBubble extends StatelessWidget {
  final QuoteData quote;

  const _QuoteBubble({required this.quote});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: AppStyles.spacingL),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: AppColors.backgroundSecondary,
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(4),
                topRight: Radius.circular(18),
                bottomLeft: Radius.circular(18),
                bottomRight: Radius.circular(18),
              ),
            ),
            child: Text(
              quote.quote.replaceAll(RegExp(r'^"|"$'), ''),
              style: const TextStyle(color: AppColors.textPrimary, fontSize: 15, height: 1.5),
            ),
          ),
          const SizedBox(height: AppStyles.spacingS),
          Padding(
            padding: const EdgeInsets.only(left: AppStyles.spacingXS),
            child: Row(
              children: [
                Text(
                  '— ${quote.speaker}',
                  style: const TextStyle(color: AppColors.textTertiary, fontSize: 13, fontWeight: FontWeight.w500),
                ),
                if (quote.time.isNotEmpty) ...[
                  const Text(' · ', style: TextStyle(color: AppColors.textQuaternary, fontSize: 13)),
                  Text(
                    quote.time,
                    style: const TextStyle(
                      color: AppColors.textQuaternary,
                      fontSize: 12,
                      fontFeatures: [FontFeature.tabularFigures()],
                    ),
                  ),
                ],
                if (quote.recordStatus != QuoteRecordStatus.onTheRecord) ...[
                  const Text(' · ', style: TextStyle(color: AppColors.textQuaternary, fontSize: 13)),
                  Text(
                    quote.recordStatus.displayName,
                    style: TextStyle(color: quote.recordStatus.color, fontSize: 12, fontWeight: FontWeight.w500),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}
