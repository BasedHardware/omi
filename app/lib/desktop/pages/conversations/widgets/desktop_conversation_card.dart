import 'package:flutter/material.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';

/// Premium minimal conversation card matching desktop design language
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

class _DesktopConversationCardState extends State<DesktopConversationCard> {
  bool _isHovered = false;

  @override
  Widget build(BuildContext context) {
    return MouseRegion(
      onEnter: (_) => setState(() => _isHovered = true),
      onExit: (_) => setState(() => _isHovered = false),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: widget.onTap,
          borderRadius: BorderRadius.circular(8),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 150),
            curve: Curves.easeOut,
            width: double.maxFinite,
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: _isHovered ? ResponsiveHelper.backgroundQuaternary : ResponsiveHelper.backgroundTertiary,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(
                color: _isHovered
                    ? ResponsiveHelper.purplePrimary.withOpacity(0.3)
                    : ResponsiveHelper.backgroundQuaternary.withOpacity(0.6),
                width: 1,
              ),
              boxShadow: _isHovered
                  ? [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.15),
                        blurRadius: 8,
                        offset: const Offset(0, 2),
                      ),
                    ]
                  : [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.1),
                        blurRadius: 4,
                        offset: const Offset(0, 1),
                      ),
                    ],
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header with clean minimal design
                _buildHeader(),

                if (!widget.conversation.discarded) ...[
                  const SizedBox(height: 12),

                  // Title with clean typography
                  Text(
                    widget.conversation.structured.title.decodeString,
                    style: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w500,
                      color: ResponsiveHelper.textPrimary,
                      height: 1.3,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),

                  const SizedBox(height: 6),

                  // Overview with clean styling
                  Text(
                    widget.conversation.structured.overview.decodeString,
                    style: const TextStyle(
                      fontSize: 13,
                      color: ResponsiveHelper.textSecondary,
                      height: 1.4,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ] else ...[
                  const SizedBox(height: 8),

                  // For discarded conversations, show transcript
                  Text(
                    widget.conversation.getTranscript(maxCount: 100),
                    style: const TextStyle(
                      fontSize: 13,
                      color: ResponsiveHelper.textSecondary,
                      height: 1.4,
                    ),
                    maxLines: 3,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        // Emoji + Tag section with clean styling
        Expanded(
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Emoji with consistent styling
              if (!widget.conversation.discarded)
                Text(
                  widget.conversation.structured.getEmoji(),
                  style: const TextStyle(
                    fontSize: 18,
                    fontWeight: FontWeight.w400,
                  ),
                ),

              // Category tag with minimal design
              if (widget.conversation.structured.category.isNotEmpty && !widget.conversation.discarded)
                const SizedBox(width: 8),
              if (widget.conversation.structured.category.isNotEmpty)
                Flexible(
                  child: Container(
                    decoration: BoxDecoration(
                      color: widget.conversation.getTagColor(),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    child: Text(
                      widget.conversation.getTag(),
                      style: TextStyle(
                        fontSize: 11,
                        fontWeight: FontWeight.w500,
                        color: widget.conversation.getTagTextColor(),
                      ),
                      overflow: TextOverflow.ellipsis,
                      maxLines: 1,
                    ),
                  ),
                ),
            ],
          ),
        ),

        const SizedBox(width: 12),

        // Timestamp + Duration with clean design
        Column(
          crossAxisAlignment: CrossAxisAlignment.end,
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              dateTimeFormat(
                'MMM d, h:mm a',
                widget.conversation.startedAt ?? widget.conversation.createdAt,
              ),
              style: const TextStyle(
                color: ResponsiveHelper.textTertiary,
                fontSize: 12,
                fontWeight: FontWeight.w400,
              ),
              maxLines: 1,
            ),
            if (widget.conversation.transcriptSegments.isNotEmpty && _getConversationDuration().isNotEmpty) ...[
              const SizedBox(height: 3),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundPrimary.withOpacity(0.8),
                  borderRadius: BorderRadius.circular(3),
                ),
                child: Text(
                  _getConversationDuration(),
                  style: const TextStyle(
                    color: ResponsiveHelper.textTertiary,
                    fontSize: 10,
                    fontWeight: FontWeight.w500,
                  ),
                  maxLines: 1,
                ),
              ),
            ],
          ],
        ),
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
