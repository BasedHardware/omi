import 'package:flutter/material.dart';
import '../models/quote_board_data.dart';

/// Widget for rendering a board of journalist quotes from LLM-generated data
class QuoteBoardWidget extends StatefulWidget {
  final QuoteBoardDisplayData data;
  static const int _initialVisibleCount = 3;

  const QuoteBoardWidget({
    super.key,
    required this.data,
  });

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

  void _navigateToAllQuotes() {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => AllQuotesScreen(data: widget.data),
      ),
    );
  }

  Widget _buildToggleButton() {
    return GestureDetector(
      onTap: _toggleExpanded,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.08),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              _isExpanded ? Icons.expand_less : Icons.expand_more,
              size: 18,
              color: Colors.white.withOpacity(0.7),
            ),
            const SizedBox(width: 6),
            Text(
              _isExpanded
                  ? 'Show less'
                  : 'Show ${widget.data.quotes.length - QuoteBoardWidget._initialVisibleCount} more',
              style: TextStyle(
                color: Colors.white.withOpacity(0.7),
                fontSize: 13,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSeeAllButton() {
    return GestureDetector(
      onTap: _navigateToAllQuotes,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
        decoration: BoxDecoration(
          color: Colors.white.withOpacity(0.08),
          borderRadius: BorderRadius.circular(20),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              'See all ${widget.data.quotes.length} quotes',
              style: TextStyle(
                color: Colors.white.withOpacity(0.7),
                fontSize: 13,
                fontWeight: FontWeight.w500,
              ),
            ),
            const SizedBox(width: 4),
            Icon(
              Icons.arrow_forward_ios,
              size: 12,
              color: Colors.white.withOpacity(0.5),
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
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Title
          const Padding(
            padding: EdgeInsets.only(bottom: 12),
            child: Text(
              'Quote Board',
              style: TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),

          // Quotes with smooth animation
          AnimatedSize(
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeInOut,
            alignment: Alignment.topCenter,
            child: Stack(
              children: [
                Column(
                  children: visibleQuotes.map((quote) => _QuoteBubble(quote: quote)).toList(),
                ),

                // Gradient fade overlay with button when collapsed
                if (hasMore && !_isExpanded)
                  Positioned(
                    bottom: 0,
                    left: 0,
                    right: 0,
                    child: AnimatedOpacity(
                      opacity: _isExpanded ? 0.0 : 1.0,
                      duration: const Duration(milliseconds: 200),
                      child: Container(
                        height: 120,
                        decoration: const BoxDecoration(
                          gradient: LinearGradient(
                            begin: Alignment.topCenter,
                            end: Alignment.bottomCenter,
                            stops: [0.0, 0.6, 1.0],
                            colors: [
                              Colors.transparent,
                              Color(0xEE000000),
                              Colors.black,
                            ],
                          ),
                        ),
                        child: Align(
                          alignment: Alignment.bottomCenter,
                          child: Padding(
                            padding: const EdgeInsets.only(bottom: 8),
                            child: _buildToggleButton(),
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),

          // Buttons when expanded
          AnimatedOpacity(
            opacity: (hasMore && _isExpanded) ? 1.0 : 0.0,
            duration: const Duration(milliseconds: 200),
            child: AnimatedSlide(
              offset: (hasMore && _isExpanded) ? Offset.zero : const Offset(0, -0.5),
              duration: const Duration(milliseconds: 300),
              curve: Curves.easeOut,
              child: (hasMore && _isExpanded)
                  ? Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          _buildToggleButton(),
                          const SizedBox(width: 12),
                          _buildSeeAllButton(),
                        ],
                      ),
                    )
                  : const SizedBox.shrink(),
            ),
          ),
        ],
      ),
    );
  }
}

/// Full screen to display all quotes
class AllQuotesScreen extends StatelessWidget {
  final QuoteBoardDisplayData data;

  const AllQuotesScreen({
    super.key,
    required this.data,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F0F0F),
      appBar: AppBar(
        title: Text(
          'All Quotes (${data.quotes.length})',
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w600,
            color: Colors.white,
          ),
        ),
        backgroundColor: const Color(0xFF0F0F0F),
        elevation: 0,
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: ListView.builder(
        padding: const EdgeInsets.all(16),
        itemCount: data.quotes.length,
        itemBuilder: (context, index) {
          return _QuoteBubble(quote: data.quotes[index]);
        },
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
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Speech bubble
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: Colors.white.withOpacity(0.08),
              borderRadius: const BorderRadius.only(
                topLeft: Radius.circular(4),
                topRight: Radius.circular(18),
                bottomLeft: Radius.circular(18),
                bottomRight: Radius.circular(18),
              ),
            ),
            child: Text(
              quote.quote.replaceAll(RegExp(r'^"|"$'), ''),
              style: const TextStyle(
                color: Colors.white,
                fontSize: 15,
                height: 1.5,
              ),
            ),
          ),

          const SizedBox(height: 8),

          // Attribution row
          Padding(
            padding: const EdgeInsets.only(left: 4),
            child: Row(
              children: [
                // Speaker name
                Text(
                  '— ${quote.speaker}',
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.7),
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),

                // Time
                if (quote.time.isNotEmpty) ...[
                  Text(
                    ' · ',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.3),
                      fontSize: 13,
                    ),
                  ),
                  Text(
                    quote.time,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.4),
                      fontSize: 12,
                      fontFeatures: const [FontFeature.tabularFigures()],
                    ),
                  ),
                ],

                // Record status (subtle)
                if (quote.recordStatus != QuoteRecordStatus.onTheRecord) ...[
                  Text(
                    ' · ',
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.3),
                      fontSize: 13,
                    ),
                  ),
                  Text(
                    quote.recordStatus.displayName,
                    style: TextStyle(
                      color: quote.recordStatus.color.withOpacity(0.7),
                      fontSize: 12,
                      fontWeight: FontWeight.w500,
                    ),
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
