import 'package:flutter/material.dart';
import '../models/timeline_data.dart';

/// Widget for rendering a chronological story timeline from LLM-generated data
class TimelineWidget extends StatefulWidget {
  final TimelineDisplayData data;
  static const int _initialVisibleCount = 5;

  const TimelineWidget({
    super.key,
    required this.data,
  });

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
                  : 'Show ${widget.data.events.length - TimelineWidget._initialVisibleCount} more events',
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
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Title
          if (widget.data.title != null && widget.data.title!.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: Text(
                widget.data.title!,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ),

          // Timeline events with smooth animation
          AnimatedSize(
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeInOut,
            alignment: Alignment.topCenter,
            child: Stack(
              children: [
                Column(
                  children: visibleEvents.asMap().entries.map((entry) {
                    final index = entry.key;
                    final event = entry.value;
                    final isLastVisible = index == visibleEvents.length - 1;
                    final isActualLast = index == widget.data.events.length - 1;

                    return _TimelineEventItem(
                      event: event,
                      isLast: _isExpanded ? isActualLast : isLastVisible,
                    );
                  }).toList(),
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
                        height: 140,
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

          // Show less button when expanded
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
                      child: Center(child: _buildToggleButton()),
                    )
                  : const SizedBox.shrink(),
            ),
          ),
        ],
      ),
    );
  }
}

class _TimelineEventItem extends StatelessWidget {
  final TimelineEventData event;
  final bool isLast;

  const _TimelineEventItem({
    required this.event,
    required this.isLast,
  });

  @override
  Widget build(BuildContext context) {
    return IntrinsicHeight(
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Timeline line and dot
          SizedBox(
            width: 24,
            child: Column(
              children: [
                // Spacer to align dot with badges (badges are ~22px tall, dot is 10px)
                const SizedBox(height: 6),
                // Dot
                Container(
                  width: 10,
                  height: 10,
                  decoration: BoxDecoration(
                    color: event.labelType.color,
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: event.labelType.color.withOpacity(0.4),
                        blurRadius: 4,
                        spreadRadius: 1,
                      ),
                    ],
                  ),
                ),
                // Connecting line
                if (!isLast)
                  Expanded(
                    child: Container(
                      width: 2,
                      color: Colors.white.withOpacity(0.2),
                    ),
                  ),
              ],
            ),
          ),

          const SizedBox(width: 12),

          // Event content
          Expanded(
            child: Padding(
              padding: EdgeInsets.only(bottom: isLast ? 0 : 16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Time and label row
                  Row(
                    children: [
                      // Time badge
                      if (event.time.isNotEmpty)
                        Container(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 6,
                            vertical: 2,
                          ),
                          decoration: BoxDecoration(
                            color: Colors.white.withOpacity(0.1),
                            borderRadius: BorderRadius.circular(4),
                          ),
                          child: Text(
                            event.time,
                            style: TextStyle(
                              color: Colors.white.withOpacity(0.7),
                              fontSize: 12,
                              fontWeight: FontWeight.w500,
                              fontFeatures: const [FontFeature.tabularFigures()],
                            ),
                          ),
                        ),

                      if (event.time.isNotEmpty) const SizedBox(width: 8),

                      // Label chip
                      Container(
                        padding: const EdgeInsets.symmetric(
                          horizontal: 8,
                          vertical: 3,
                        ),
                        decoration: BoxDecoration(
                          color: event.labelType.color.withOpacity(0.15),
                          borderRadius: BorderRadius.circular(4),
                        ),
                        child: Text(
                          event.label,
                          style: TextStyle(
                            color: event.labelType.color,
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                      ),
                    ],
                  ),

                  const SizedBox(height: 6),

                  // Description
                  Text(
                    event.description,
                    style: TextStyle(
                      color: Colors.white.withOpacity(0.9),
                      fontSize: 15,
                      height: 1.5,
                    ),
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
