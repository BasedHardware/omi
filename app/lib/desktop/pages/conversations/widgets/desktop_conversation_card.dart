import 'package:flutter/material.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';

class DesktopConversationCard extends StatefulWidget {
  final ServerConversation conversation;
  final VoidCallback onTap;

  const DesktopConversationCard({
    super.key,
    required this.conversation,
    required this.onTap,
  });

  @override
  State<DesktopConversationCard> createState() => _DesktopConversationCardState();
}

class _DesktopConversationCardState extends State<DesktopConversationCard> with SingleTickerProviderStateMixin {
  bool _isHovered = false;
  late AnimationController _animationController;
  late Animation<double> _scaleAnimation;
  late Animation<double> _elevationAnimation;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 200),
      vsync: this,
    );

    _scaleAnimation = Tween<double>(
      begin: 1.0,
      end: 1.02,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeOutCubic,
    ));

    _elevationAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeOutCubic,
    ));
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) {
        setState(() => _isHovered = true);
        _animationController.forward();
      },
      onExit: (_) {
        setState(() => _isHovered = false);
        _animationController.reverse();
      },
      child: AnimatedBuilder(
        animation: _animationController,
        builder: (context, child) {
          return Transform.scale(
            scale: _scaleAnimation.value,
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: widget.onTap,
                borderRadius: BorderRadius.circular(16),
                child: Container(
                  width: double.maxFinite,
                  margin: const EdgeInsets.only(bottom: 4),
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.05),
                    borderRadius: BorderRadius.circular(16),
                    border: Border.all(
                      color: _isHovered ? ResponsiveHelper.purplePrimary.withOpacity(0.4) : ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                      width: 1,
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.08 + (_elevationAnimation.value * 0.12)),
                        blurRadius: 12 + (_elevationAnimation.value * 8),
                        offset: Offset(0, 4 + (_elevationAnimation.value * 4)),
                        spreadRadius: _elevationAnimation.value * 2,
                      ),
                      if (_isHovered)
                        BoxShadow(
                          color: ResponsiveHelper.purplePrimary.withOpacity(0.01),
                          blurRadius: 20,
                          offset: const Offset(0, 8),
                        ),
                    ],
                  ),
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(16),
                    child: Container(
                      padding: const EdgeInsets.all(20),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // Modern header with better visual hierarchy
                          _buildModernHeader(),

                          const SizedBox(height: 16),

                          // Content section with improved layout
                          _buildContentSection(),

                          const SizedBox(height: 14),

                          // Footer with metadata
                          _buildFooter(),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  Widget _buildModernHeader() {
    return Row(
      children: [
        // Conversation icon with modern styling
        Container(
          width: 40,
          height: 40,
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
              colors: [
                ResponsiveHelper.purplePrimary.withOpacity(0.2),
                ResponsiveHelper.purplePrimary.withOpacity(0.1),
              ],
            ),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: ResponsiveHelper.purplePrimary.withOpacity(0.2),
              width: 1,
            ),
          ),
          child: Center(
            child: Text(
              widget.conversation.structured.getEmoji(),
              style: const TextStyle(fontSize: 18),
            ),
          ),
        ),

        const SizedBox(width: 12),

        // Title section (moved from content section)
        Expanded(
          child: Text(
            widget.conversation.discarded ? 'Discarded Conversation' : (widget.conversation.structured.title.isNotEmpty ? widget.conversation.structured.title.decodeString : 'Untitled Conversation'),
            style: const TextStyle(
              fontSize: 18, // Increased by 2 points from 16
              fontWeight: FontWeight.w600,
              color: ResponsiveHelper.textPrimary,
              height: 1.3,
              letterSpacing: -0.2,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),

        const SizedBox(width: 8),

        // Category chip (moved from left side)
        if (widget.conversation.structured.category.isNotEmpty && !widget.conversation.discarded)
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: BoxDecoration(
              color: ResponsiveHelper.purplePrimary.withOpacity(0.15),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                width: 1,
              ),
            ),
            child: Text(
              widget.conversation.getTag(),
              style: const TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.w600,
                color: ResponsiveHelper.purplePrimary,
                letterSpacing: 0.3,
              ),
              overflow: TextOverflow.ellipsis,
              maxLines: 1,
            ),
          ),

        const SizedBox(width: 8),

        // Status indicators
        _buildStatusIndicators(),
      ],
    );
  }

  Widget _buildStatusIndicators() {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        // Duration indicator
        if (widget.conversation.transcriptSegments.isNotEmpty && _getConversationDuration().isNotEmpty) ...[
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.6),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  FontAwesomeIcons.clock,
                  size: 12,
                  color: ResponsiveHelper.textTertiary,
                ),
                const SizedBox(width: 4),
                Text(
                  _getConversationDuration(),
                  style: const TextStyle(
                    color: ResponsiveHelper.textTertiary,
                    fontSize: 10,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
        ],

        // Action items indicator
        if (widget.conversation.structured.actionItems.isNotEmpty) ...[
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: ResponsiveHelper.purplePrimary.withOpacity(0.15),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  FontAwesomeIcons.listCheck,
                  size: 10,
                  color: ResponsiveHelper.purplePrimary,
                ),
                const SizedBox(width: 4),
                Text(
                  '${widget.conversation.structured.actionItems.length}',
                  style: const TextStyle(
                    color: ResponsiveHelper.purplePrimary,
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(width: 8),
        ],
      ],
    );
  }

  Widget _buildContentSection() {
    if (widget.conversation.discarded) {
      return Text(
        widget.conversation.getTranscript(maxCount: 150),
        style: const TextStyle(
          fontSize: 14,
          color: ResponsiveHelper.textSecondary,
          height: 1.5,
        ),
        maxLines: 3,
        overflow: TextOverflow.ellipsis,
      );
    }

    // Only show overview/description now, title moved to header
    return Text(
      widget.conversation.structured.overview.decodeString,
      style: const TextStyle(
        fontSize: 14, // Keep same size as requested
        color: ResponsiveHelper.textSecondary,
        height: 1.5,
      ),
      maxLines: 2,
      overflow: TextOverflow.ellipsis,
    );
  }

  Widget _buildFooter() {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Timestamp with icon (left aligned with description)
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
            borderRadius: BorderRadius.circular(6),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(
                FontAwesomeIcons.calendar,
                size: 12,
                color: ResponsiveHelper.textTertiary,
              ),
              const SizedBox(width: 4),
              Text(
                dateTimeFormat(
                  'MMM d, h:mm a',
                  widget.conversation.startedAt ?? widget.conversation.createdAt,
                ),
                style: const TextStyle(
                  color: ResponsiveHelper.textTertiary,
                  fontSize: 11,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
        ),

        const Spacer(),

        // Additional metadata
        if (widget.conversation.transcriptSegments.isNotEmpty) ...[
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
              borderRadius: BorderRadius.circular(6),
            ),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                const Icon(
                  FontAwesomeIcons.microphone,
                  size: 12,
                  color: ResponsiveHelper.textTertiary,
                ),
                const SizedBox(width: 4),
                Text(
                  '${widget.conversation.transcriptSegments.length} segments',
                  style: const TextStyle(
                    color: ResponsiveHelper.textTertiary,
                    fontSize: 11,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ],
            ),
          ),
        ],
      ],
    );
  }

  String _getConversationDuration() {
    if (widget.conversation.transcriptSegments.isEmpty) return '';

    // Get the total duration in seconds
    int durationSeconds = widget.conversation.getDurationInSeconds();
    if (durationSeconds <= 0) return '';

    return secondsToCompactDuration(durationSeconds);
  }
}
