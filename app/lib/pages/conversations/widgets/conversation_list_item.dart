import 'dart:async';

import 'package:flutter/material.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/structured.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
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
                confirmDismiss: (direction) {
                  bool showDeleteConfirmation = SharedPreferencesUtil().showConversationDeleteConfirmation;
                  if (!showDeleteConfirmation) return Future.value(true);
                  final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                  if (connectivityProvider.isConnected) {
                    return showDialog(
                        context: context,
                        builder: (context) {
                          return StatefulBuilder(
                            builder: (context, setState) {
                              return ConfirmationDialog(
                                title: "Delete Conversation?",
                                description:
                                    "Are you sure you want to delete this conversation? This action cannot be undone.",
                                checkboxValue: !showDeleteConfirmation,
                                checkboxText: "Don't ask me again",
                                onCheckboxChanged: (value) {
                                  setState(() {
                                    showDeleteConfirmation = !value;
                                  });
                                },
                                onCancel: () => Navigator.of(context).pop(),
                                onConfirm: () {
                                  SharedPreferencesUtil().showConversationDeleteConfirmation = showDeleteConfirmation;
                                  return Navigator.pop(context, true);
                                },
                              );
                            },
                          );
                        });
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
                              style: Theme.of(context)
                                  .textTheme
                                  .bodyMedium!
                                  .copyWith(color: Colors.grey.shade300, height: 1.3),
                              maxLines: 2,
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
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          widget.conversation.discarded
              ? const SizedBox.shrink()
              : Text(widget.conversation.structured.getEmoji(),
                  style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w500)),
          widget.conversation.structured.category.isNotEmpty && !widget.conversation.discarded
              ? const SizedBox(width: 12)
              : const SizedBox.shrink(),
          widget.conversation.structured.category.isNotEmpty
              ? Container(
                  decoration: BoxDecoration(
                    color: widget.conversation.getTagColor(),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  child: Text(
                    widget.conversation.getTag(),
                    style:
                        Theme.of(context).textTheme.bodyMedium!.copyWith(color: widget.conversation.getTagTextColor()),
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
                    style: TextStyle(color: Colors.grey.shade400, fontSize: 14),
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
