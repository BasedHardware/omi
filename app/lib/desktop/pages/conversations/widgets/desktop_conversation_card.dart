import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:share_plus/share_plus.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/ui/atoms/omi_avatar.dart';
import 'package:omi/ui/atoms/omi_badge.dart';
import 'package:omi/ui/atoms/omi_button.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
import 'package:omi/ui/molecules/omi_edit_dialog.dart';
import 'package:omi/ui/molecules/omi_context_menu.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/conversation_provider.dart';

class DesktopConversationCard extends StatefulWidget {
  final ServerConversation conversation;
  final VoidCallback onTap;
  final int index;
  final DateTime date;

  const DesktopConversationCard({
    super.key,
    required this.conversation,
    required this.onTap,
    required this.index,
    required this.date,
  });

  @override
  State<DesktopConversationCard> createState() => _DesktopConversationCardState();
}

class _DesktopConversationCardState extends State<DesktopConversationCard> with SingleTickerProviderStateMixin {
  bool _isHovered = false;
  bool _isSharing = false;
  late AnimationController _animationController;
  late Animation<double> _scaleAnimation;
  late Animation<double> _elevationAnimation;
  late Animation<double> _actionBarAnimation;

  @override
  void initState() {
    super.initState();
    _animationController = AnimationController(
      duration: const Duration(milliseconds: 250),
      vsync: this,
    );

    _scaleAnimation = Tween<double>(
      begin: 1.0,
      end: 1.01,
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

    _actionBarAnimation = Tween<double>(
      begin: 0.0,
      end: 1.0,
    ).animate(CurvedAnimation(
      parent: _animationController,
      curve: Curves.easeOutQuart,
    ));
  }

  @override
  void dispose() {
    _animationController.dispose();
    super.dispose();
  }

  void _showDeleteConfirmation() async {
    final confirmed = await OmiConfirmDialog.show(
      context,
      title: 'Delete Conversation',
      message: 'Are you sure you want to delete this conversation? This action cannot be undone.',
      confirmLabel: 'Delete',
      cancelLabel: 'Cancel',
      confirmColor: ResponsiveHelper.errorColor,
    );

    if (confirmed == true) {
      _deleteConversation();
    }
  }

  void _deleteConversation() {
    final provider = Provider.of<ConversationProvider>(context, listen: false);
    provider.deleteConversationLocally(widget.conversation, widget.index, widget.date);

    // Show simple delete confirmation snackbar (no undo for now)
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Row(
          children: [
            Icon(
              Icons.check_circle_outline_rounded,
              color: ResponsiveHelper.successColor,
              size: 20,
            ),
            SizedBox(width: 12),
            Text(
              'Conversation deleted',
              style: TextStyle(
                color: ResponsiveHelper.textPrimary,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
        backgroundColor: ResponsiveHelper.backgroundTertiary,
        behavior: SnackBarBehavior.floating,
        margin: const EdgeInsets.all(16),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        duration: const Duration(seconds: 2),
      ),
    );
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
      child: Focus(
        onKeyEvent: (node, event) {
          if (event is KeyDownEvent) {
            if (event.logicalKey == LogicalKeyboardKey.delete) {
              _showDeleteConfirmation();
              return KeyEventResult.handled;
            }
          }
          return KeyEventResult.ignored;
        },
        child: GestureDetector(
          onSecondaryTapDown: _showContextMenu,
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
                        color: Colors.white.withValues(alpha: 0.05),
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(
                          color: _isHovered
                              ? ResponsiveHelper.purplePrimary.withValues(alpha: 0.4)
                              : ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3),
                          width: 1,
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.black.withValues(alpha: 0.08 + (_elevationAnimation.value * 0.12)),
                            blurRadius: 12 + (_elevationAnimation.value * 8),
                            offset: Offset(0, 4 + (_elevationAnimation.value * 4)),
                            spreadRadius: _elevationAnimation.value * 2,
                          ),
                          if (_isHovered)
                            BoxShadow(
                              color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.01),
                              blurRadius: 20,
                              offset: const Offset(0, 8),
                            ),
                        ],
                      ),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(16),
                        child: Column(
                          children: [
                            // Main card content
                            Container(
                              padding: const EdgeInsets.all(20),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  // Modern header with integrated action area
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

                            // Action bar that slides up on hover
                            if (_isHovered)
                              SizeTransition(
                                sizeFactor: _actionBarAnimation,
                                axisAlignment: -1.0,
                                child: Container(
                                  width: double.infinity,
                                  height: 44,
                                  decoration: BoxDecoration(
                                    color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.8),
                                    border: Border(
                                      top: BorderSide(
                                        color: ResponsiveHelper.backgroundQuaternary.withValues(alpha: 0.5),
                                        width: 1,
                                      ),
                                    ),
                                  ),
                                  child: Row(
                                    children: [
                                      const SizedBox(width: 16),

                                      // Delete action using OmiButton
                                      Tooltip(
                                        message: 'Delete conversation (Del)',
                                        decoration: BoxDecoration(
                                          color: ResponsiveHelper.backgroundTertiary,
                                          borderRadius: BorderRadius.circular(6),
                                        ),
                                        textStyle: const TextStyle(
                                          color: ResponsiveHelper.textPrimary,
                                          fontSize: 12,
                                        ),
                                        child: OmiButton(
                                          label: 'Delete',
                                          icon: Icons.delete_outline_rounded,
                                          type: OmiButtonType.neutral,
                                          color: ResponsiveHelper.errorColor,
                                          onPressed: () {
                                            HapticFeedback.lightImpact();
                                            _showDeleteConfirmation();
                                          },
                                        ),
                                      ),

                                      const Spacer(),

                                      // Additional actions hint
                                      const Text(
                                        'Right-click for more options',
                                        style: TextStyle(
                                          fontSize: 11,
                                          color: ResponsiveHelper.textTertiary,
                                        ),
                                      ),

                                      const SizedBox(width: 16),
                                    ],
                                  ),
                                ),
                              ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }

  void _showContextMenu(TapDownDetails details) async {
    final menuItems = [
      OmiContextMenuItem(
        id: 'share',
        title: _isSharing ? 'Sharing...' : 'Share conversation',
        subtitle: _isSharing ? '' : 'Create shareable link',
        icon: _isSharing ? Icons.hourglass_empty : Icons.share_outlined,
        iconColor: _isSharing ? ResponsiveHelper.textTertiary : ResponsiveHelper.purplePrimary,
        backgroundColor: _isSharing
            ? ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3)
            : ResponsiveHelper.purplePrimary.withValues(alpha: 0.1),
        enabled: !_isSharing,
      ),
      OmiContextMenuItem(
        id: 'copy_link',
        title: _isSharing ? 'Generating link...' : 'Copy link',
        subtitle: _isSharing ? '' : 'Copy shareable link',
        icon: _isSharing ? Icons.hourglass_empty : Icons.link_outlined,
        iconColor: _isSharing ? ResponsiveHelper.textTertiary : ResponsiveHelper.purplePrimary,
        backgroundColor: _isSharing
            ? ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3)
            : ResponsiveHelper.purplePrimary.withValues(alpha: 0.1),
        enabled: !_isSharing,
      ),
      OmiContextMenuItem(
        id: 'copy',
        title: 'Copy transcript',
        subtitle: 'Copy to clipboard',
        icon: Icons.copy_outlined,
        iconColor: ResponsiveHelper.infoColor,
        backgroundColor: ResponsiveHelper.infoColor.withValues(alpha: 0.1),
      ),
      OmiContextMenuItem(
        id: 'edit',
        title: 'Edit conversation',
        subtitle: 'Change title',
        icon: Icons.edit_outlined,
        iconColor: ResponsiveHelper.warningColor,
        backgroundColor: ResponsiveHelper.warningColor.withValues(alpha: 0.1),
      ),
      OmiContextMenuItem(
        id: 'delete',
        title: 'Delete conversation',
        subtitle: 'Cannot be undone',
        icon: Icons.delete_outline_rounded,
        iconColor: ResponsiveHelper.errorColor,
        backgroundColor: ResponsiveHelper.errorColor.withValues(alpha: 0.1),
      ),
    ];

    final result = await OmiContextMenu.show(
      context,
      position: details.globalPosition,
      items: menuItems,
      showDividerBeforeLast: true,
    );

    if (result != null) {
      _handleContextMenuAction(result);
    }
  }

  void _handleContextMenuAction(String action) {
    switch (action) {
      case 'share':
        if (!_isSharing) _shareConversation();
        break;
      case 'copy_link':
        if (!_isSharing) _copyConversationLink();
        break;
      case 'copy':
        _copyConversation();
        break;
      case 'edit':
        _editConversation();
        break;
      case 'delete':
        _showDeleteConfirmation();
        break;
    }
  }

  Future<void> _shareConversation() async {
    if (_isSharing) return;
    setState(() => _isSharing = true);

    try {
      bool shared = await setConversationVisibility(widget.conversation.id);
      if (!shared) {
        _showSnackBar('Conversation URL could not be shared.');
        setState(() => _isSharing = false);
        return;
      }

      String content = 'https://h.omi.me/conversations/${widget.conversation.id}';
      await Share.share(content);
    } catch (e) {
      _showSnackBar('Failed to generate share link');
    } finally {
      setState(() => _isSharing = false);
    }
  }

  Future<void> _copyConversationLink() async {
    if (_isSharing) return;
    setState(() => _isSharing = true);

    try {
      bool shared = await setConversationVisibility(widget.conversation.id);
      if (!shared) {
        _showSnackBar('Conversation URL could not be generated.');
        setState(() => _isSharing = false);
        return;
      }

      String content = 'https://h.omi.me/conversations/${widget.conversation.id}';
      await Clipboard.setData(ClipboardData(text: content));

      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Row(
            children: [
              Icon(
                Icons.check_circle_outline_rounded,
                color: ResponsiveHelper.successColor,
                size: 20,
              ),
              SizedBox(width: 12),
              Text(
                'Conversation link copied to clipboard',
                style: TextStyle(
                  color: ResponsiveHelper.textPrimary,
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
          backgroundColor: ResponsiveHelper.backgroundTertiary,
          behavior: SnackBarBehavior.floating,
          margin: const EdgeInsets.all(16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
          duration: const Duration(seconds: 2),
        ),
      );
    } catch (e) {
      _showSnackBar('Failed to generate conversation link');
    } finally {
      setState(() => _isSharing = false);
    }
  }

  void _showSnackBar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Row(
          children: [
            const Icon(
              Icons.check_circle_outline_rounded,
              color: ResponsiveHelper.successColor,
              size: 20,
            ),
            const SizedBox(width: 12),
            Text(
              message,
              style: const TextStyle(
                color: ResponsiveHelper.textPrimary,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
        backgroundColor: ResponsiveHelper.backgroundTertiary,
        behavior: SnackBarBehavior.floating,
        margin: const EdgeInsets.all(16),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  void _copyConversation() {
    // Copy conversation text to clipboard
    final text = widget.conversation.getTranscript();
    Clipboard.setData(ClipboardData(text: text));

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: const Row(
          children: [
            Icon(
              Icons.check_circle_outline_rounded,
              color: ResponsiveHelper.successColor,
              size: 20,
            ),
            SizedBox(width: 12),
            Text(
              'Conversation transcript copied to clipboard',
              style: TextStyle(
                color: ResponsiveHelper.textPrimary,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
        backgroundColor: ResponsiveHelper.backgroundTertiary,
        behavior: SnackBarBehavior.floating,
        margin: const EdgeInsets.all(16),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
        ),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  void _editConversation() async {
    final currentTitle = widget.conversation.structured.title.isNotEmpty
        ? widget.conversation.structured.title.decodeString
        : 'Untitled Conversation';

    final newTitle = await OmiEditDialog.show(
      context,
      title: 'Edit Conversation',
      subtitle: 'Change the conversation title',
      currentValue: currentTitle,
      icon: Icons.edit_outlined,
      fieldLabel: 'Conversation Title',
      fieldHint: 'Enter conversation title...',
      maxLines: 2,
    );

    if (newTitle != null && newTitle.isNotEmpty) {
      await _updateConversationTitle(newTitle);
    }
  }

  Future<void> _updateConversationTitle(String newTitle) async {
    try {
      final success = await updateConversationTitle(widget.conversation.id, newTitle);

      if (success) {
        // Update the conversation locally by modifying the structured title
        widget.conversation.structured.title = newTitle;

        // Update in provider
        final provider = Provider.of<ConversationProvider>(context, listen: false);
        provider.updateConversationInSortedList(widget.conversation);

        _showSnackBar('Conversation title updated successfully');
      } else {
        _showSnackBar('Failed to update conversation title');
      }
    } catch (e) {
      _showSnackBar('Error updating conversation title');
    }
  }

  Widget _buildModernHeader() {
    return Row(
      children: [
        // Avatar with emoji fallback
        OmiAvatar(
          size: 40,
          fallback: Center(
            child: Text(
              widget.conversation.structured.getEmoji(),
              style: const TextStyle(fontSize: 18),
            ),
          ),
        ),

        const SizedBox(width: 12),

        // Title section
        Expanded(
          child: Text(
            widget.conversation.discarded
                ? 'Discarded Conversation'
                : (widget.conversation.structured.title.isNotEmpty
                    ? widget.conversation.structured.title.decodeString
                    : 'Untitled Conversation'),
            style: const TextStyle(
              fontSize: 18,
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

        // Status indicators (keep existing badges)
        _buildStatusIndicators(),
      ],
    );
  }

  Widget _buildStatusIndicators() {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        // Category chip
        if (widget.conversation.structured.category.isNotEmpty && !widget.conversation.discarded) ...[
          OmiBadge(label: widget.conversation.getTag()),
          const SizedBox(width: 8),
        ],

        // Duration indicator
        if (widget.conversation.transcriptSegments.isNotEmpty && _getConversationDuration().isNotEmpty) ...[
          OmiBadge(
            label: _getConversationDuration(),
            color: ResponsiveHelper.textTertiary,
          ),
          const SizedBox(width: 8),
        ],

        // Action items indicator
        if (widget.conversation.structured.actionItems.isNotEmpty) ...[
          OmiBadge(
            label: '${widget.conversation.structured.actionItems.length}',
            color: ResponsiveHelper.purplePrimary,
          ),
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

    return Text(
      widget.conversation.structured.overview.decodeString,
      style: const TextStyle(
        fontSize: 14,
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
        // Timestamp
        OmiBadge(
          label: dateTimeFormat(
            'MMM d, h:mm a',
            widget.conversation.startedAt ?? widget.conversation.createdAt,
          ),
          color: ResponsiveHelper.textTertiary,
        ),

        const Spacer(),

        // Additional metadata
        if (widget.conversation.transcriptSegments.isNotEmpty) ...[
          OmiBadge(
            label: '${widget.conversation.transcriptSegments.length} segments',
            color: ResponsiveHelper.textTertiary,
          ),
        ],
      ],
    );
  }

  String _getConversationDuration() {
    if (widget.conversation.transcriptSegments.isEmpty) return '';

    int durationSeconds = widget.conversation.getDurationInSeconds();
    if (durationSeconds <= 0) return '';

    return secondsToCompactDuration(durationSeconds);
  }
}
