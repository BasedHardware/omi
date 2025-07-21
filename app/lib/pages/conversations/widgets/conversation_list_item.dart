import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/widgets/confirmation_dialog.dart';
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
          MixpanelManager().conversationListItemClicked(widget.conversation, widget.conversationIdx);
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
          padding: EdgeInsets.only(top: 12, left: widget.isFromOnboarding ? 0 : 16, right: widget.isFromOnboarding ? 0 : 16),
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
                      builder: (c) => getDialog(context, () => Navigator.pop(context), () => Navigator.pop(context), 'Unable to Delete Conversation', 'Please check your internet connection and try again.', singleButton: true, okButtonText: 'OK'),
                      context: context,
                    );
                  }
                },
                onDismissed: (direction) async {
                  var conversation = widget.conversation;
                  var conversationIdx = widget.conversationIdx;
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
                      widget.conversation.discarded
                          ? const SizedBox.shrink()
                          : Text(
                              structured.title.decodeString,
                              style: Theme.of(context).textTheme.titleLarge,
                              maxLines: 1,
                            ),
                      widget.conversation.discarded ? const SizedBox.shrink() : const SizedBox(height: 8),
                      widget.conversation.discarded
                          ? const SizedBox.shrink()
                          : Text(
                              structured.overview.decodeString,
                              style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade300, height: 1.3),
                              maxLines: 2,
                            ),
                      widget.conversation.discarded
                          ? Column(
                              children: [
                                if (widget.conversation.photos.isNotEmpty)
                                  Row(children: [
                                    Icon(
                                      Icons.photo_library,
                                      color: Colors.grey.shade400,
                                      size: 18,
                                    ),
                                    SizedBox(
                                      width: 12,
                                    ),
                                    Text(
                                      "${widget.conversation.photos.length} photos",
                                      style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade300, height: 1.3),
                                    )
                                  ]),
                                Text(
                                  widget.conversation.getTranscript(maxCount: 100),
                                  style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: Colors.grey.shade300, height: 1.3),
                                ),
                              ],
                            )
                          : const SizedBox(height: 8),
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

  _getConversationHeader() {
    return Padding(
      padding: const EdgeInsets.only(left: 4.0, right: 12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          // 🧠 Emoji + Tag
          Flexible(
            fit: FlexFit.tight,
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                if (!widget.conversation.discarded)
                  Text(
                    widget.conversation.structured.getEmoji(),
                    style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w500),
                  ),
                if (widget.conversation.structured.category.isNotEmpty && !widget.conversation.discarded) const SizedBox(width: 8),
                if (widget.conversation.structured.category.isNotEmpty)
                  Flexible(
                    child: Container(
                      decoration: BoxDecoration(
                        color: widget.conversation.getTagColor(),
                        borderRadius: BorderRadius.circular(16),
                      ),
                      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                      child: Text(
                        widget.conversation.getTag(),
                        style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: widget.conversation.getTagTextColor()),
                        overflow: TextOverflow.ellipsis,
                        maxLines: 1,
                      ),
                    ),
                  ),
              ],
            ),
          ),

          const SizedBox(width: 12),

          // 🕒 Timestamp + Duration or New
          FittedBox(
            fit: BoxFit.scaleDown,
            child: isNew
                ? const ConversationNewStatusIndicator(text: "New 🚀")
                : Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        dateTimeFormat(
                          'MMM d, h:mm a',
                          widget.conversation.startedAt ?? widget.conversation.createdAt,
                        ),
                        style: const TextStyle(color: Color(0xFF6A6B71), fontSize: 14),
                        maxLines: 1,
                      ),
                      if (widget.conversation.transcriptSegments.isNotEmpty && _getConversationDuration().isNotEmpty)
                        Padding(
                          padding: const EdgeInsets.only(left: 8.0),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: const Color(0xFF35343B),
                              borderRadius: BorderRadius.circular(4),
                            ),
                            child: Text(
                              _getConversationDuration(),
                              style: const TextStyle(color: Colors.white, fontSize: 11),
                              maxLines: 1,
                            ),
                          ),
                        ),
                    ],
                  ),
          ),
        ],
      ),
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

class ConversationNewStatusIndicator extends StatefulWidget {
  final String text;

  const ConversationNewStatusIndicator({super.key, required this.text});

  @override
  State<ConversationNewStatusIndicator> createState() => _ConversationNewStatusIndicatorState();
}

class _ConversationNewStatusIndicatorState extends State<ConversationNewStatusIndicator> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  late Animation<double> _opacityAnim;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      duration: const Duration(milliseconds: 1000), // Blink every half second
      vsync: this,
    )..repeat(reverse: true);
    _opacityAnim = Tween<double>(begin: 1.0, end: 0.2).animate(_controller);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FadeTransition(
      opacity: _opacityAnim,
      child: Text(widget.text),
    );
  }
}
