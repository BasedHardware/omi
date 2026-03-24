import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/pages/settings/usage_page.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';

/// Premium compact conversation card with Apple-quality design.
/// Features:
/// - App icon showing which app processed the conversation
/// - App name + category badge
/// - Subtle gradient background
/// - All metadata: duration, source, action items
/// - No emojis - icons only
class ConversationListItemCompact extends StatefulWidget {
  final bool isFromOnboarding;
  final DateTime date;
  final int conversationIdx;
  final ServerConversation conversation;

  const ConversationListItemCompact({
    super.key,
    required this.conversation,
    required this.date,
    required this.conversationIdx,
    this.isFromOnboarding = false,
  });

  @override
  State<ConversationListItemCompact> createState() => _ConversationListItemCompactState();
}

class _ConversationListItemCompactState extends State<ConversationListItemCompact> {
  Timer? _conversationNewStatusResetTimer;
  bool isNew = false;

  @override
  void dispose() {
    _conversationNewStatusResetTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Check if conversation is new (within 60 seconds)
    DateTime memorizedAt = widget.conversation.createdAt;
    if (widget.conversation.finishedAt != null && widget.conversation.finishedAt!.isAfter(memorizedAt)) {
      memorizedAt = widget.conversation.finishedAt!;
    }
    int seconds = (DateTime.now().millisecondsSinceEpoch - memorizedAt.millisecondsSinceEpoch) ~/ 1000;
    isNew = 0 < seconds && seconds < 60;
    if (isNew) {
      _conversationNewStatusResetTimer?.cancel();
      _conversationNewStatusResetTimer = Timer(const Duration(seconds: 60), () async {
        setState(() {
          isNew = false;
        });
      });
    }

    return Consumer<ConversationProvider>(builder: (context, provider, child) {
      return GestureDetector(
        onTap: () async {
          if (widget.conversation.isLocked) {
            MixpanelManager().paywallOpened('Conversation List Item Compact');
            routeToPage(context, const UsagePage(showUpgradeDialog: true));
            return;
          }

          int hoursSinceConversation = DateTime.now().difference(widget.conversation.createdAt).inHours;

          String searchQuery = provider.previousQuery;
          if (searchQuery.isNotEmpty) {
            MixpanelManager().conversationOpenedFromSearch(
              conversation: widget.conversation,
              searchQuery: searchQuery,
              conversationIndexInResults: widget.conversationIdx,
            );
          } else {
            MixpanelManager().conversationListItemClickedWithTimeDifference(
              conversation: widget.conversation,
              conversationIndex: widget.conversationIdx,
              hoursSinceConversation: hoursSinceConversation,
            );
          }

          context.read<ConversationDetailProvider>().updateConversation(widget.conversation.id, widget.date);
          String startingTitle = context.read<ConversationDetailProvider>().conversation.structured.title;
          provider.onConversationTap(widget.conversation.id);

          await routeToPage(
            context,
            ConversationDetailPage(conversation: widget.conversation, isFromOnboarding: widget.isFromOnboarding),
          );
          if (mounted) {
            String newTitle = context.read<ConversationDetailProvider>().conversation.structured.title;
            if (startingTitle != newTitle) {
              widget.conversation.structured.title = newTitle;
              provider.upsertConversation(widget.conversation);
            }
          }
        },
        child: Padding(
          padding: EdgeInsets.only(
            top: 12,
            left: widget.isFromOnboarding ? 0 : 16,
            right: widget.isFromOnboarding ? 0 : 16,
          ),
          child: Container(
            width: double.maxFinite,
            decoration: BoxDecoration(
              // Subtle gradient for premium depth
              gradient: const LinearGradient(
                begin: Alignment.topLeft,
                end: Alignment.bottomRight,
                colors: [
                  Color(0xFF1A1A1F),
                  Color(0xFF151518),
                ],
              ),
              borderRadius: BorderRadius.circular(12.0),
              border: Border.all(
                color: Colors.white.withValues(alpha: 0.06),
                width: 0.5,
              ),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(12.0),
              child: Dismissible(
                key: UniqueKey(),
                direction: DismissDirection.endToStart,
                background: Container(
                  alignment: Alignment.centerRight,
                  padding: const EdgeInsets.only(right: 20.0),
                  color: Colors.red,
                  child: const Icon(Icons.delete, color: Colors.white),
                ),
                confirmDismiss: (direction) async {
                  HapticFeedback.mediumImpact();
                  bool showDeleteConfirmation = SharedPreferencesUtil().showConversationDeleteConfirmation;
                  if (!showDeleteConfirmation) return Future.value(true);
                  final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                  if (connectivityProvider.isConnected) {
                    return await showDialog(
                      context: context,
                      builder: (ctx) => getDialog(
                        context,
                        () => Navigator.of(context).pop(false),
                        () => Navigator.of(context).pop(true),
                        'Delete Conversation?',
                        'Are you sure you want to delete this conversation? This action cannot be undone.',
                        okButtonText: 'Confirm',
                      ),
                    );
                  } else {
                    return showDialog(
                      builder: (c) => getDialog(context, () => Navigator.pop(context), () => Navigator.pop(context),
                          'Unable to Delete Conversation', 'Please check your internet connection and try again.',
                          singleButton: true, okButtonText: 'OK'),
                      context: context,
                    );
                  }
                },
                onDismissed: (direction) async {
                  var conversation = widget.conversation;
                  var conversationIdx = widget.conversationIdx;
                  MixpanelManager().conversationSwipedToDelete(conversation);
                  provider.deleteConversationLocally(conversation, conversationIdx, widget.date);
                },
                child: Padding(
                  padding: const EdgeInsets.all(14),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      _buildHeaderRow(),
                      const SizedBox(height: 6),
                      _buildCategoryRow(),
                      if (!widget.conversation.discarded) ...[
                        const SizedBox(height: 10),
                        _buildOverview(),
                        const SizedBox(height: 12),
                        _buildMetadataRow(),
                      ] else ...[
                        const SizedBox(height: 10),
                        _buildDiscardedContent(),
                      ],
                    ],
                  ),
                ),
              ),
            ),
          ),
        ),
      );
    });
  }

  /// Header row: Title + Time + New indicator
  Widget _buildHeaderRow() {
    final structured = widget.conversation.structured;

    return Row(
      children: [
        // Title
        Expanded(
          child: Text(
            widget.conversation.discarded ? 'Discarded' : structured.title.decodeString,
            style: const TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.w600,
              color: Colors.white,
              height: 1.2,
              letterSpacing: -0.2,
            ),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ),
        const SizedBox(width: 8),
        // New indicator (subtle dot)
        if (isNew) ...[
          Container(
            width: 5,
            height: 5,
            decoration: const BoxDecoration(
              color: Color(0xFF22c55e),
              shape: BoxShape.circle,
            ),
          ),
          const SizedBox(width: 6),
        ],
        // Time chip
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.06),
            borderRadius: BorderRadius.circular(4),
          ),
          child: Text(
            dateTimeFormat(
              'h:mm a',
              widget.conversation.startedAt ?? widget.conversation.createdAt,
            ),
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w500,
              color: Colors.white.withValues(alpha: 0.5),
              letterSpacing: -0.1,
            ),
          ),
        ),
      ],
    );
  }

  /// Category row: Category badge
  Widget _buildCategoryRow() {
    final categoryColors = _getCategoryColors();

    return Row(
      children: [
        // Category badge with icon
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
          decoration: BoxDecoration(
            color: (categoryColors['bgColor'] as Color).withValues(alpha: 0.6),
            borderRadius: BorderRadius.circular(4),
            border: Border.all(
              color: (categoryColors['color'] as Color).withValues(alpha: 0.3),
              width: 0.5,
            ),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                _getCategoryIcon(),
                size: 10,
                color: categoryColors['color'] as Color,
              ),
              const SizedBox(width: 3),
              Text(
                widget.conversation.getTag(),
                style: TextStyle(
                  color: categoryColors['color'] as Color,
                  fontSize: 10,
                  fontWeight: FontWeight.w600,
                  letterSpacing: -0.1,
                ),
              ),
            ],
          ),
        ),
      ],
    );
  }

  /// Overview text (two lines max)
  Widget _buildOverview() {
    final structured = widget.conversation.structured;

    if (structured.overview.isEmpty) {
      return const SizedBox.shrink();
    }

    return Text(
      structured.overview.decodeString,
      style: TextStyle(
        fontSize: 13,
        fontWeight: FontWeight.w400,
        color: Colors.white.withValues(alpha: 0.6),
        height: 1.3,
        letterSpacing: -0.1,
      ),
      maxLines: 2,
      overflow: TextOverflow.ellipsis,
    );
  }

  /// Metadata row: Duration, Source, Action items
  Widget _buildMetadataRow() {
    final duration = _getConversationDuration();
    final source = widget.conversation.source;
    final actionItemsCount = widget.conversation.structured.actionItems.length;

    return Row(
      children: [
        // Duration
        if (duration.isNotEmpty) ...[
          _buildMiniChip(
            icon: Icons.schedule_outlined,
            label: duration,
          ),
          const SizedBox(width: 6),
        ],
        // Source device
        if (source != null) ...[
          _buildMiniChip(
            icon: _getSourceIcon(source),
            label: _getSourceLabel(source),
            color: const Color(0xFF8b5cf6),
          ),
          const SizedBox(width: 6),
        ],
        // Action items count
        if (actionItemsCount > 0)
          _buildMiniChipFA(
            icon: FontAwesomeIcons.listCheck,
            label: '$actionItemsCount',
            color: const Color(0xFF22c55e),
          ),
        const Spacer(),
        // Completion indicator
        if (widget.conversation.status == ConversationStatus.completed)
          Icon(
            Icons.check,
            size: 12,
            color: const Color(0xFF34d399).withValues(alpha: 0.6),
          ),
        // Locked indicator
        if (widget.conversation.isLocked)
          Icon(
            Icons.lock_outline,
            size: 12,
            color: Colors.white.withValues(alpha: 0.4),
          ),
      ],
    );
  }

  /// Mini chip for metadata
  Widget _buildMiniChip({
    required IconData icon,
    required String label,
    Color? color,
  }) {
    final chipColor = color ?? Colors.white.withValues(alpha: 0.4);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
      decoration: BoxDecoration(
        color: chipColor.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 10, color: chipColor),
          const SizedBox(width: 3),
          Text(
            label,
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w500,
              color: chipColor,
              letterSpacing: -0.1,
            ),
          ),
        ],
      ),
    );
  }

  /// Mini chip for metadata with FontAwesome icon
  Widget _buildMiniChipFA({
    required IconData icon,
    required String label,
    Color? color,
  }) {
    final chipColor = color ?? Colors.white.withValues(alpha: 0.4);
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
      decoration: BoxDecoration(
        color: chipColor.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(4),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          FaIcon(icon, size: 9, color: chipColor),
          const SizedBox(width: 3),
          Text(
            label,
            style: TextStyle(
              fontSize: 10,
              fontWeight: FontWeight.w500,
              color: chipColor,
              letterSpacing: -0.1,
            ),
          ),
        ],
      ),
    );
  }

  /// Discarded content view
  Widget _buildDiscardedContent() {
    return Text(
      widget.conversation.getTranscript(maxCount: 80),
      style: TextStyle(
        fontSize: 13,
        color: Colors.white.withValues(alpha: 0.5),
        height: 1.3,
      ),
      maxLines: 1,
      overflow: TextOverflow.ellipsis,
    );
  }

  IconData _getSourceIcon(ConversationSource source) {
    switch (source) {
      case ConversationSource.omi:
        return Icons.memory;
      case ConversationSource.friend:
        return Icons.people;
      case ConversationSource.openglass:
        return Icons.visibility;
      case ConversationSource.screenpipe:
        return Icons.screen_share;
      case ConversationSource.phone:
        return Icons.phone_android;
      case ConversationSource.desktop:
        return Icons.computer;
      case ConversationSource.apple_watch:
        return Icons.watch;
      default:
        return Icons.devices;
    }
  }

  String _getSourceLabel(ConversationSource source) {
    switch (source) {
      case ConversationSource.omi:
        return 'Omi';
      case ConversationSource.friend:
        return 'Friend';
      case ConversationSource.openglass:
        return 'Glass';
      case ConversationSource.screenpipe:
        return 'Screen';
      case ConversationSource.phone:
        return 'Phone';
      case ConversationSource.desktop:
        return 'Desktop';
      case ConversationSource.apple_watch:
        return 'Watch';
      case ConversationSource.sdcard:
        return 'SD Card';
      case ConversationSource.workflow:
        return 'Workflow';
      default:
        return source.name;
    }
  }

  Map<String, Color> _getCategoryColors() {
    String category = widget.conversation.structured.category.toLowerCase();

    if (category.contains('work') || category.contains('business') || category.contains('meeting') || category.contains('project')) {
      return {'color': const Color(0xFF60a5fa), 'bgColor': const Color(0xFF1e3a5f)};
    } else if (category.contains('personal') || category.contains('family')) {
      return {'color': const Color(0xFFa78bfa), 'bgColor': const Color(0xFF2e1065)};
    } else if (category.contains('health') || category.contains('fitness')) {
      return {'color': const Color(0xFF34d399), 'bgColor': const Color(0xFF064e3b)};
    } else if (category.contains('finance') || category.contains('shopping')) {
      return {'color': const Color(0xFFfb923c), 'bgColor': const Color(0xFF431407)};
    } else if (category.contains('entertainment') || category.contains('music') || category.contains('sports')) {
      return {'color': const Color(0xFFf472b6), 'bgColor': const Color(0xFF4a044e)};
    } else if (category.contains('technology') || category.contains('education')) {
      return {'color': const Color(0xFF22d3ee), 'bgColor': const Color(0xFF164e63)};
    } else if (category.contains('food') || category.contains('restaurant')) {
      return {'color': const Color(0xFFfb923c), 'bgColor': const Color(0xFF431407)};
    } else if (category.contains('travel')) {
      return {'color': const Color(0xFF22d3ee), 'bgColor': const Color(0xFF164e63)};
    } else {
      return {'color': const Color(0xFFa78bfa), 'bgColor': const Color(0xFF2e1065)};
    }
  }

  IconData _getCategoryIcon() {
    String category = widget.conversation.structured.category.toLowerCase();

    if (category.contains('work') || category.contains('business')) {
      return Icons.business_center_outlined;
    } else if (category.contains('meeting') || category.contains('conference')) {
      return Icons.calendar_today_outlined;
    } else if (category.contains('project')) {
      return Icons.folder_outlined;
    } else if (category.contains('personal') || category.contains('life')) {
      return Icons.person_outline;
    } else if (category.contains('family')) {
      return Icons.people_outline;
    } else if (category.contains('health') || category.contains('medical')) {
      return Icons.favorite_outline;
    } else if (category.contains('fitness') || category.contains('exercise') || category.contains('workout')) {
      return Icons.fitness_center_outlined;
    } else if (category.contains('finance') || category.contains('money') || category.contains('banking')) {
      return Icons.attach_money;
    } else if (category.contains('shopping') || category.contains('purchase')) {
      return Icons.shopping_bag_outlined;
    } else if (category.contains('entertainment') || category.contains('fun') || category.contains('movie')) {
      return Icons.movie_outlined;
    } else if (category.contains('music')) {
      return Icons.music_note_outlined;
    } else if (category.contains('sports') || category.contains('game')) {
      return Icons.sports_outlined;
    } else if (category.contains('education') || category.contains('learning') || category.contains('school')) {
      return Icons.school_outlined;
    } else if (category.contains('technology') || category.contains('tech') || category.contains('coding')) {
      return Icons.computer_outlined;
    } else if (category.contains('travel') || category.contains('trip') || category.contains('vacation')) {
      return Icons.flight_outlined;
    } else if (category.contains('food') || category.contains('restaurant') || category.contains('dining')) {
      return Icons.restaurant_outlined;
    } else if (category.contains('home') || category.contains('house')) {
      return Icons.home_outlined;
    } else if (category.contains('task') || category.contains('todo')) {
      return Icons.check_box_outlined;
    } else if (category.contains('idea') || category.contains('brainstorm')) {
      return Icons.lightbulb_outline;
    } else if (category.contains('note')) {
      return Icons.note_outlined;
    } else if (category.contains('event')) {
      return Icons.event_outlined;
    } else if (category.contains('social') || category.contains('friends')) {
      return Icons.people_outline;
    } else if (category.contains('creative') || category.contains('art')) {
      return Icons.palette_outlined;
    } else {
      return Icons.chat_bubble_outline;
    }
  }

  String _getConversationDuration() {
    int durationSeconds = widget.conversation.getDurationInSeconds();
    if (durationSeconds <= 0) return '';
    return secondsToCompactDuration(durationSeconds);
  }
}
