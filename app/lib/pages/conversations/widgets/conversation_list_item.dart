import 'dart:async';
import 'dart:ui';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
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

class ConversationListItem extends StatefulWidget {
  final bool isFromOnboarding;
  final DateTime date;
  final int conversationIdx;
  final ServerConversation conversation;

  const ConversationListItem({
    super.key,
    required this.conversation,
    required this.date,
    required this.conversationIdx,
    this.isFromOnboarding = false,
  });

  @override
  State<ConversationListItem> createState() => _ConversationListItemState();
}

class _ConversationListItemState extends State<ConversationListItem> {
  Timer? _conversationNewStatusResetTimer;
  bool isNew = false;

  @override
  void dispose() {
    _conversationNewStatusResetTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Is new conversation
    DateTime memorizedAt = widget.conversation.createdAt;
    if (widget.conversation.finishedAt != null && widget.conversation.finishedAt!.isAfter(memorizedAt)) {
      memorizedAt = widget.conversation.finishedAt!;
    }
    int seconds = (DateTime.now().millisecondsSinceEpoch - memorizedAt.millisecondsSinceEpoch) ~/ 1000;
    isNew = 0 < seconds && seconds < 60; // 1m
    if (isNew) {
      _conversationNewStatusResetTimer?.cancel();
      _conversationNewStatusResetTimer = Timer(const Duration(seconds: 60), () async {
        setState(() {
          isNew = false;
        });
      });
    }

    Structured structured = widget.conversation.structured;
    return Consumer<ConversationProvider>(builder: (context, provider, child) {
      return GestureDetector(
        onTap: () async {
          if (widget.conversation.isLocked) {
            MixpanelManager().paywallOpened('Conversation List Item');
            routeToPage(context, const UsagePage(showUpgradeDialog: true));
            return;
          }

          // Calculate time difference
          int hoursSinceConversation = DateTime.now().difference(widget.conversation.createdAt).inHours;

          // Check if user is searching
          String searchQuery = provider.previousQuery;
          if (searchQuery.isNotEmpty) {
            // Track conversation opened from search
            MixpanelManager().conversationOpenedFromSearch(
              conversation: widget.conversation,
              searchQuery: searchQuery,
              conversationIndexInResults: widget.conversationIdx,
            );
          } else {
            // Track normal conversation list item click with time difference
            MixpanelManager().conversationListItemClickedWithTimeDifference(
              conversation: widget.conversation,
              conversationIndex: widget.conversationIdx,
              hoursSinceConversation: hoursSinceConversation,
            );
          }

          context.read<ConversationDetailProvider>().updateConversation(widget.conversationIdx, widget.date);
          String startingTitle = context.read<ConversationDetailProvider>().conversation.structured.title;
          provider.onConversationTap(widget.conversationIdx);

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
          padding:
              EdgeInsets.only(top: 12, left: widget.isFromOnboarding ? 0 : 16, right: widget.isFromOnboarding ? 0 : 16),
          child: Container(
            width: double.maxFinite,
            decoration: BoxDecoration(
              color: const Color(0xFF1F1F25),
              borderRadius: BorderRadius.circular(16.0),
            ),
            child: ClipRRect(
              borderRadius: BorderRadius.circular(16.0),
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
                  padding: const EdgeInsetsDirectional.all(16),
                  child: Column(
                    mainAxisSize: MainAxisSize.max,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _getConversationHeader(),
                      const SizedBox(height: 16),
                      _buildConversationBody(context),
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

  Widget _buildConversationBody(BuildContext context) {
    if (widget.conversation.discarded) {
      return Stack(
        children: [
          Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              if (widget.conversation.photos.isNotEmpty) ...[
                Row(children: [
                  Icon(
                    Icons.photo_library,
                    color: Colors.grey.shade400,
                    size: 18,
                  ),
                  const SizedBox(width: 12),
                  Text(
                    "${widget.conversation.photos.length} photos",
                    style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade300, height: 1.3),
                  )
                ]),
                const SizedBox(height: 4),
              ],
              Text(
                widget.conversation.getTranscript(maxCount: 100),
                style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade300, height: 1.3),
              ),
            ],
          ),
          if (widget.conversation.isLocked) _buildLockedOverlay(),
        ],
      );
    }

    final structured = widget.conversation.structured;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Title
        Text(
          structured.title.decodeString,
          style: const TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w600,
            height: 1.3,
            color: Colors.white,
          ),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        const SizedBox(height: 6),
        // Overview/Description
        Text(
          structured.overview.decodeString,
          style: TextStyle(
            fontSize: 14,
            height: 1.3,
            color: Colors.white.withOpacity(0.7),
          ),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        const SizedBox(height: 12),
        // Footer with time and duration as simple text
        _buildFooter(),
      ],
    );
  }

  Widget _buildFooter() {
    return Row(
      children: [
        // Time
        Text(
          dateTimeFormat(
            'h:mm a',
            widget.conversation.startedAt ?? widget.conversation.createdAt,
          ),
          style: TextStyle(
            fontSize: 12,
            color: Colors.white.withOpacity(0.5),
            height: 1.3,
          ),
        ),
        const SizedBox(width: 12),
        // Duration
        if (_getConversationDuration().isNotEmpty)
          Text(
            _getConversationDuration(),
            style: TextStyle(
              fontSize: 12,
              color: Colors.white.withOpacity(0.5),
              height: 1.3,
            ),
          ),
      ],
    );
  }

  Widget _buildLockedOverlay() {
    return Positioned.fill(
      child: ClipRRect(
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 3.0, sigmaY: 3.0),
          child: Container(
            alignment: Alignment.center,
            decoration: BoxDecoration(
              color: Colors.black.withValues(alpha: 0.01),
              borderRadius: const BorderRadius.all(Radius.circular(8)),
            ),
            child: const Text(
              'Upgrade to unlimited',
              style: TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
          ),
        ),
      ),
    );
  }

  _getConversationHeader() {
    final categoryColors = _getCategoryColors();

    return Row(
      children: [
        // Category Badge with Icon and colored background
        Container(
          decoration: BoxDecoration(
            color: categoryColors['bgColor'],
            borderRadius: BorderRadius.circular(4),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(
                _getCategoryIcon(),
                size: 14,
                color: categoryColors['color'],
              ),
              const SizedBox(width: 5),
              Text(
                widget.conversation.getTag(),
                style: TextStyle(
                  color: categoryColors['color'],
                  fontSize: 11,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
        const SizedBox(width: 8),
        // Completion icon
        if (widget.conversation.status == ConversationStatus.completed)
          const Icon(
            Icons.check_circle,
            size: 10,
            color: Color(0xFF34d399),
          ),
      ],
    );
  }

  Map<String, Color> _getCategoryColors() {
    String category = widget.conversation.structured.category.toLowerCase();

    // Dark mode colors matching the reference
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
      // Default purple for "Personal"
      return {'color': const Color(0xFFa78bfa), 'bgColor': const Color(0xFF2e1065)};
    }
  }

  IconData _getCategoryIcon() {
    // Map category names to icons (comprehensive mapping)
    String category = widget.conversation.structured.category.toLowerCase();

    // Work & Business
    if (category.contains('work') || category.contains('business')) {
      return Icons.business_center_outlined;
    } else if (category.contains('meeting') || category.contains('conference')) {
      return Icons.calendar_today_outlined;
    } else if (category.contains('project')) {
      return Icons.folder_outlined;
    }

    // Personal & Family
    else if (category.contains('personal') || category.contains('life')) {
      return Icons.person_outline;
    } else if (category.contains('family')) {
      return Icons.people_outline;
    }

    // Health & Wellness
    else if (category.contains('health') || category.contains('medical')) {
      return Icons.favorite_outline;
    } else if (category.contains('fitness') || category.contains('exercise') || category.contains('workout')) {
      return Icons.fitness_center_outlined;
    }

    // Finance & Shopping
    else if (category.contains('finance') || category.contains('money') || category.contains('banking')) {
      return Icons.attach_money;
    } else if (category.contains('shopping') || category.contains('purchase')) {
      return Icons.shopping_bag_outlined;
    }

    // Entertainment & Leisure
    else if (category.contains('entertainment') || category.contains('fun') || category.contains('movie')) {
      return Icons.movie_outlined;
    } else if (category.contains('music')) {
      return Icons.music_note_outlined;
    } else if (category.contains('sports') || category.contains('game')) {
      return Icons.sports_outlined;
    }

    // Education & Technology
    else if (category.contains('education') || category.contains('learning') || category.contains('school')) {
      return Icons.school_outlined;
    } else if (category.contains('technology') || category.contains('tech') || category.contains('coding')) {
      return Icons.computer_outlined;
    }

    // Travel & Food
    else if (category.contains('travel') || category.contains('trip') || category.contains('vacation')) {
      return Icons.flight_outlined;
    } else if (category.contains('food') || category.contains('restaurant') || category.contains('dining')) {
      return Icons.restaurant_outlined;
    }

    // Home & Other
    else if (category.contains('home') || category.contains('house')) {
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
    } else if (category.contains('car') || category.contains('vehicle') || category.contains('transport')) {
      return Icons.directions_car_outlined;
    } else if (category.contains('pet') || category.contains('animal')) {
      return Icons.pets_outlined;
    } else if (category.contains('book') || category.contains('reading')) {
      return Icons.menu_book_outlined;
    } else if (category.contains('photo') || category.contains('camera')) {
      return Icons.photo_camera_outlined;
    } else {
      return Icons.chat_bubble_outline; // Default icon
    }
  }

  String _getConversationDuration() {
    int durationSeconds = widget.conversation.getDurationInSeconds();
    if (durationSeconds <= 0) return '';

    return secondsToCompactDuration(durationSeconds);
  }

  String _getTimeAgo() {
    final now = DateTime.now();
    final conversationTime = widget.conversation.startedAt ?? widget.conversation.createdAt;
    final difference = now.difference(conversationTime);

    if (difference.inDays > 7) {
      final weeks = (difference.inDays / 7).floor();
      return '${weeks}w ago';
    } else if (difference.inDays > 0) {
      return '${difference.inDays}d ago';
    } else if (difference.inHours > 0) {
      return '${difference.inHours}h ago';
    } else if (difference.inMinutes > 0) {
      return '${difference.inMinutes}m ago';
    } else {
      return 'Just now';
    }
  }
}
