import 'package:flutter/material.dart';
import '../models/followups_data.dart';

/// Widget for rendering journalist follow-up tasks from LLM-generated data
class FollowupsWidget extends StatefulWidget {
  final FollowupsDisplayData data;
  static const int _initialVisibleCount = 3;

  const FollowupsWidget({
    super.key,
    required this.data,
  });

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
                  : 'Show ${widget.data.items.length - FollowupsWidget._initialVisibleCount} more',
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

    final hasMore = widget.data.items.length > FollowupsWidget._initialVisibleCount;
    final visibleItems = _isExpanded || !hasMore
        ? widget.data.items
        : widget.data.items.take(FollowupsWidget._initialVisibleCount).toList();

    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          // Title
          Padding(
            padding: const EdgeInsets.only(bottom: 12),
            child: Row(
              children: [
                Icon(
                  Icons.checklist_rounded,
                  color: Colors.white.withOpacity(0.6),
                  size: 18,
                ),
                const SizedBox(width: 8),
                const Text(
                  'Follow-ups & Fact-checks',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),

          // Items with smooth animation
          AnimatedSize(
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeInOut,
            alignment: Alignment.topCenter,
            child: Stack(
              children: [
                Column(
                  children: visibleItems.asMap().entries.map((entry) {
                    final index = entry.key;
                    final item = entry.value;
                    final isLastVisible = index == visibleItems.length - 1;
                    final isActualLast = index == widget.data.items.length - 1;

                    return _FollowupItem(
                      item: item,
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
                        height: 100,
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

class _FollowupItem extends StatelessWidget {
  final FollowupItemData item;
  final bool isLast;

  const _FollowupItem({
    required this.item,
    required this.isLast,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: EdgeInsets.only(bottom: isLast ? 0 : 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Colored dot indicator
          Padding(
            padding: const EdgeInsets.only(top: 6),
            child: Container(
              width: 8,
              height: 8,
              decoration: BoxDecoration(
                color: item.type.color,
                shape: BoxShape.circle,
                boxShadow: [
                  BoxShadow(
                    color: item.type.color.withOpacity(0.4),
                    blurRadius: 4,
                    spreadRadius: 1,
                  ),
                ],
              ),
            ),
          ),

          const SizedBox(width: 12),

          // Content
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Type badge
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 8,
                    vertical: 3,
                  ),
                  decoration: BoxDecoration(
                    color: item.type.backgroundColor,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    item.type.displayName,
                    style: TextStyle(
                      color: item.type.color,
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),

                const SizedBox(height: 6),

                // Task text
                Text(
                  item.content,
                  style: TextStyle(
                    color: Colors.white.withOpacity(0.9),
                    fontSize: 15,
                    height: 1.5,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
