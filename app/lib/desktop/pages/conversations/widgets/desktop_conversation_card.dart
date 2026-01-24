import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/molecules/omi_confirm_dialog.dart';
import 'package:omi/ui/molecules/omi_context_menu.dart';
import 'package:omi/ui/molecules/omi_edit_dialog.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/extensions/string.dart';

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

class _DesktopConversationCardState extends State<DesktopConversationCard> {
  bool _isSharing = false;
  bool _isHovered = false;

  void _showDeleteConfirmation() async {
    final confirmed = await OmiConfirmDialog.show(
      context,
      title: context.l10n.deleteConversation,
      message: context.l10n.deleteConversationConfirmation,
      confirmLabel: context.l10n.delete,
      cancelLabel: context.l10n.cancel,
      confirmColor: ResponsiveHelper.errorColor,
    );

    if (confirmed == true) {
      _deleteConversation();
    }
  }

  void _deleteConversation() {
    final provider = Provider.of<ConversationProvider>(context, listen: false);
    provider.deleteConversationLocally(widget.conversation, widget.index, widget.date);

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
              context.l10n.conversationDeleted,
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

  @override
  Widget build(BuildContext context) {
    final duration = _getConversationDuration(context);
    final isStarred = widget.conversation.starred;

    return MouseRegion(
      cursor: SystemMouseCursors.click,
      onEnter: (_) => setState(() => _isHovered = true),
      onExit: (_) => setState(() => _isHovered = false),
      child: GestureDetector(
        onSecondaryTapDown: _showContextMenu,
        child: GestureDetector(
          onTap: () {
            if (widget.conversation.isLocked) {
              Navigator.of(context).push(
                MaterialPageRoute(
                  builder: (context) => const UsagePage(showUpgradeDialog: true),
                ),
              );
              return;
            }
            widget.onTap();
          },
          child: Container(
            width: double.maxFinite,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 16),
            decoration: BoxDecoration(
              color: _isHovered ? ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4) : Colors.transparent,
              borderRadius: BorderRadius.circular(12),
            ),
            child: Row(
              children: [
                // Emoji icon in rounded square
                Container(
                  width: 44,
                  height: 44,
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.8),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Center(
                    child: Text(
                      widget.conversation.structured.getEmoji(),
                      style: const TextStyle(fontSize: 22),
                    ),
                  ),
                ),
                const SizedBox(width: 14),
                // Title and subtitle
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        widget.conversation.discarded
                            ? context.l10n.discardedConversation
                            : (widget.conversation.structured.title.isNotEmpty
                                ? widget.conversation.structured.title.decodeString
                                : context.l10n.untitledConversation),
                        style: const TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w500,
                          color: ResponsiveHelper.textPrimary,
                          height: 1.3,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      const SizedBox(height: 4),
                      // Timestamp • Duration
                      Row(
                        children: [
                          Text(
                            _getTimeString(),
                            style: const TextStyle(
                              fontSize: 13,
                              color: ResponsiveHelper.textTertiary,
                              fontWeight: FontWeight.w400,
                            ),
                          ),
                          if (duration.isNotEmpty) ...[
                            const Text(
                              ' • ',
                              style: TextStyle(
                                fontSize: 13,
                                color: ResponsiveHelper.textTertiary,
                              ),
                            ),
                            Text(
                              duration,
                              style: const TextStyle(
                                fontSize: 13,
                                color: ResponsiveHelper.textTertiary,
                                fontWeight: FontWeight.w400,
                              ),
                            ),
                          ],
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 16),
                // Star icon if starred, or lock icon if locked
                if (isStarred)
                  const FaIcon(
                    FontAwesomeIcons.solidStar,
                    size: 14,
                    color: Colors.amber,
                  )
                else if (widget.conversation.isLocked)
                  Icon(
                    Icons.lock_outline_rounded,
                    size: 16,
                    color: ResponsiveHelper.textTertiary.withValues(alpha: 0.6),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  String _getTimeString() {
    final time = widget.conversation.startedAt ?? widget.conversation.createdAt;
    return dateTimeFormat('h:mm a', time);
  }

  String _getConversationDuration(BuildContext context) {
    if (widget.conversation.transcriptSegments.isEmpty) return '';

    int durationSeconds = widget.conversation.getDurationInSeconds();
    if (durationSeconds <= 0) return '';

    return secondsToCompactDuration(durationSeconds, context);
  }

  void _showContextMenu(TapDownDetails details) async {
    final List<OmiContextMenuItem> menuItems = [
      OmiContextMenuItem(
        id: 'copy_link',
        title: _isSharing ? context.l10n.generatingLink : context.l10n.copyLink,
        icon: _isSharing ? Icons.hourglass_empty : Icons.link_outlined,
        iconColor: _isSharing ? ResponsiveHelper.textTertiary : ResponsiveHelper.purplePrimary,
        backgroundColor: _isSharing
            ? ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.3)
            : ResponsiveHelper.purplePrimary.withValues(alpha: 0.1),
        enabled: !_isSharing,
      ),
      OmiContextMenuItem(
        id: 'copy',
        title: context.l10n.copyTranscript,
        icon: Icons.copy_outlined,
        iconColor: ResponsiveHelper.infoColor,
        backgroundColor: ResponsiveHelper.infoColor.withValues(alpha: 0.1),
      ),
      OmiContextMenuItem(
        id: 'edit',
        title: context.l10n.editConversation,
        icon: Icons.edit_outlined,
        iconColor: ResponsiveHelper.warningColor,
        backgroundColor: ResponsiveHelper.warningColor.withValues(alpha: 0.1),
      ),
      OmiContextMenuItem(
        id: 'delete',
        title: context.l10n.deleteConversation,
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
        _showSnackBar(context.l10n.conversationUrlCouldNotBeShared);
        setState(() => _isSharing = false);
        return;
      }

      String content = 'https://h.omi.me/conversations/${widget.conversation.id}';
      await Share.share(content);
    } catch (e) {
      _showSnackBar(context.l10n.failedToGenerateShareLink);
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
        _showSnackBar(context.l10n.conversationUrlCouldNotBeGenerated);
        setState(() => _isSharing = false);
        return;
      }

      String content = 'https://h.omi.me/conversations/${widget.conversation.id}';
      await Clipboard.setData(ClipboardData(text: content));

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
                context.l10n.conversationLinkCopiedToClipboard,
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
    } catch (e) {
      _showSnackBar(context.l10n.failedToGenerateConversationLink);
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
    final text = widget.conversation.getTranscript();
    Clipboard.setData(ClipboardData(text: text));

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
              context.l10n.conversationTranscriptCopiedToClipboard,
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

  void _editConversation() async {
    final currentTitle = widget.conversation.structured.title.isNotEmpty
        ? widget.conversation.structured.title.decodeString
        : context.l10n.untitledConversation;

    final newTitle = await OmiEditDialog.show(
      context,
      title: context.l10n.editConversationDialogTitle,
      subtitle: context.l10n.changeTheConversationTitle,
      currentValue: currentTitle,
      icon: Icons.edit_outlined,
      fieldLabel: context.l10n.conversationTitle,
      fieldHint: context.l10n.enterConversationTitle,
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
        widget.conversation.structured.title = newTitle;
        final provider = Provider.of<ConversationProvider>(context, listen: false);
        provider.updateConversationInSortedList(widget.conversation);
        _showSnackBar(context.l10n.conversationTitleUpdatedSuccessfully);
      } else {
        _showSnackBar(context.l10n.failedToUpdateConversationTitle);
      }
    } catch (e) {
      _showSnackBar(context.l10n.errorUpdatingConversationTitle);
    }
  }
}
