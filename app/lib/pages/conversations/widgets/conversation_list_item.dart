import 'dart:async';

import 'package:flutter/material.dart';
import 'package:friend_private/backend/schema/conversation.dart';
import 'package:friend_private/backend/schema/structured.dart';
import 'package:friend_private/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:friend_private/pages/conversation_detail/page.dart';
import 'package:friend_private/providers/conversation_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/extensions/string.dart';
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
          padding:
              EdgeInsets.only(top: 12, left: widget.isFromOnboarding ? 0 : 16, right: widget.isFromOnboarding ? 0 : 16),
          child: Container(
            width: double.maxFinite,
            decoration: BoxDecoration(
              color: Colors.grey.shade900,
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
                onDismissed: (direction) {
                  var conversation = widget.conversation;
                  var conversationIdx = widget.conversationIdx;
                  provider.deleteConversationLocally(conversation, conversationIdx, widget.date);
                  provider.deleteConversationOnServer(conversation.id);
                },
                child: Padding(
                  padding: const EdgeInsetsDirectional.all(16),
                  child: Column(
                    mainAxisSize: MainAxisSize.max,
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _getConversationHeader(),
                      const SizedBox(height: 16),
                      widget.conversation.discarded
                          ? const SizedBox.shrink()
                          : Text(widget.conversation.structured.getEmoji(),
                              style: const TextStyle(color: Colors.white, fontSize: 28, fontWeight: FontWeight.w600)),
                      !widget.conversation.discarded ? const SizedBox(height: 8) : const SizedBox.shrink(),
                      widget.conversation.discarded
                          ? const SizedBox.shrink()
                          : Text(
                              structured.title.decodeString,
                              style: Theme.of(context).textTheme.titleLarge,
                              maxLines: 2,
                            ),
                      widget.conversation.discarded ? const SizedBox.shrink() : const SizedBox(height: 8),
                      widget.conversation.discarded
                          ? const SizedBox.shrink()
                          : Text(
                              structured.overview.decodeString,
                              overflow: TextOverflow.fade,
                              style: Theme.of(context)
                                  .textTheme
                                  .bodyMedium!
                                  .copyWith(color: Colors.grey.shade300, height: 1.3),
                              maxLines: 3,
                            ),
                      widget.conversation.discarded
                          ? Text(
                              widget.conversation.getTranscript(maxCount: 100),
                              style: Theme.of(context)
                                  .textTheme
                                  .bodyMedium!
                                  .copyWith(color: Colors.grey.shade300, height: 1.3),
                            )
                          : const SizedBox(height: 8),
                      _getConversationFooter(),
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

  _getConversationFooter() {
    var convo = widget.conversation.structured;
    if (convo.actionItems.isEmpty && convo.events.isEmpty) {
      return const SizedBox.shrink();
    }
    return Padding(
      padding: const EdgeInsets.only(left: 4.0, right: 12, bottom: 8, top: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.start,
        children: [
          convo.actionItems.isNotEmpty
              ? Padding(
                  padding: const EdgeInsets.only(right: 8.0),
                  child: Row(
                    children: [
                      const Icon(
                        Icons.task_alt_outlined,
                        size: 14,
                        color: Colors.white60,
                      ),
                      const SizedBox(
                        width: 4,
                      ),
                      Text(
                        "${convo.actionItems.where((act) => act.completed).length}/${convo.actionItems.length}",
                        style: const TextStyle(
                          fontSize: 12,
                          color: Colors.white60,
                        ),
                      ),
                    ],
                  ),
                )
              : const SizedBox.shrink(),
          convo.events.isNotEmpty
              ? Row(
                  children: [
                    const Icon(
                      Icons.event_outlined,
                      size: 14,
                      color: Colors.white60,
                    ),
                    const SizedBox(
                      width: 4,
                    ),
                    Text(
                      "${convo.events.length}",
                      style: const TextStyle(fontSize: 12, color: Colors.white60),
                    ),
                  ],
                )
              : const SizedBox.shrink(),
        ],
      ),
    );
  }

  _getConversationHeader() {
    return Padding(
      padding: const EdgeInsets.only(left: 4.0, right: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          widget.conversation.structured.category.isNotEmpty
              ? Container(
                  decoration: BoxDecoration(
                    borderRadius: BorderRadius.circular(16),
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: 0, vertical: 4),
                  child: Text(
                    widget.conversation.getTag(),
                    style:
                        Theme.of(context).textTheme.bodySmall!.copyWith(color: widget.conversation.getTagTextColor()),
                    maxLines: 1,
                  ),
                )
              : const SizedBox.shrink(),
          const SizedBox(
            width: 16,
          ),
          Expanded(
            child: isNew
                ? const Align(
                    alignment: Alignment.centerRight,
                    child: ConversationNewStatusIndicator(text: "New 🚀"),
                  )
                : Text(
                    dateTimeFormat('MMM d, h:mm a', widget.conversation.startedAt ?? widget.conversation.createdAt),
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 12),
                    maxLines: 1,
                    textAlign: TextAlign.end,
                  ),
          )
        ],
      ),
    );
  }
}

class ConversationNewStatusIndicator extends StatefulWidget {
  final String text;

  const ConversationNewStatusIndicator({super.key, required this.text});

  @override
  State<ConversationNewStatusIndicator> createState() => _ConversationNewStatusIndicatorState();
}

class _ConversationNewStatusIndicatorState extends State<ConversationNewStatusIndicator>
    with SingleTickerProviderStateMixin {
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
