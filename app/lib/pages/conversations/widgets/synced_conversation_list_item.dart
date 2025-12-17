import 'package:flutter/material.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/other/time_utils.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';

class SyncedConversationListItem extends StatefulWidget {
  final DateTime date;
  final int conversationIdx;
  final ServerConversation conversation;
  final bool showReprocess;

  const SyncedConversationListItem({
    super.key,
    required this.conversation,
    required this.date,
    required this.conversationIdx,
    this.showReprocess = false,
  });

  @override
  State<SyncedConversationListItem> createState() => _SyncedConversationListItemState();
}

class _SyncedConversationListItemState extends State<SyncedConversationListItem> {
  bool isReprocessing = false;
  late ServerConversation conversation;

  void setReprocessing(bool value) {
    isReprocessing = value;
    setState(() {});
  }

  @override
  void initState() {
    setState(() {
      conversation = widget.conversation;
    });
    super.initState();
  }

  @override
  void dispose() {
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    // Is new conversation
    DateTime memorizedAt = conversation.createdAt;
    if (conversation.finishedAt != null && conversation.finishedAt!.isAfter(memorizedAt)) {
      memorizedAt = conversation.finishedAt!;
    }

    return GestureDetector(
      onTap: () async {
        context.read<ConversationDetailProvider>().updateConversation(widget.conversation.id, widget.date);
        Provider.of<ConversationProvider>(context, listen: false).onConversationTap(widget.conversationIdx);
        routeToPage(
          context,
          ConversationDetailPage(conversation: widget.conversation, isFromOnboarding: false),
        );
      },
      child: Padding(
        padding: const EdgeInsets.only(top: 12, left: 16, right: 16),
        child: Container(
          width: double.maxFinite,
          decoration: BoxDecoration(
            color: const Color(0xFF1F1F25),
            borderRadius: BorderRadius.circular(24.0),
          ),
          child: Padding(
            padding: const EdgeInsetsDirectional.all(16),
            child: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Flexible(
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      _getConversationHeader(),
                      const SizedBox(height: 16),
                      conversation.discarded
                          ? Text(
                              conversation.transcriptSegments.first.text.decodeString,
                              style: Theme.of(context).textTheme.titleLarge,
                              maxLines: 1,
                            )
                          : Text(
                              conversation.structured.title.decodeString,
                              style: Theme.of(context).textTheme.titleLarge,
                              maxLines: 1,
                            ),
                      conversation.discarded ? const SizedBox.shrink() : const SizedBox(height: 8),
                    ],
                  ),
                ),
                widget.showReprocess || conversation.discarded
                    ? GestureDetector(
                        onTap: () async {
                          setReprocessing(true);
                          var mem = await reProcessConversationServer(conversation.id);
                          if (mem != null) {
                            setState(() {
                              conversation = mem;
                            });
                            context.read<ConversationProvider>().updateSyncedConversation(mem);
                          }
                          setReprocessing(false);
                        },
                        child: isReprocessing
                            ? const Center(
                                child: Padding(
                                  padding: EdgeInsets.all(8.0),
                                  child: SizedBox(
                                    height: 20,
                                    width: 20,
                                    child: CircularProgressIndicator(
                                      color: Colors.white,
                                    ),
                                  ),
                                ),
                              )
                            : Padding(
                                padding: const EdgeInsets.all(8.0),
                                child: Icon(
                                  Icons.refresh_outlined,
                                  color: Colors.grey.shade400,
                                ),
                              ),
                      )
                    : const SizedBox.shrink(),
              ],
            ),
          ),
        ),
      ),
    );
  }

  _getConversationHeader() {
    return Padding(
      padding: const EdgeInsets.only(left: 4.0, right: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          conversation.discarded
              ? const SizedBox.shrink()
              : Text(conversation.structured.getEmoji(),
                  style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w500)),
          conversation.structured.category.isNotEmpty && !conversation.discarded
              ? const SizedBox(width: 12)
              : const SizedBox.shrink(),
          conversation.structured.category.isNotEmpty
              ? Container(
                  decoration: BoxDecoration(
                    color: conversation.getTagColor(),
                    borderRadius: BorderRadius.circular(16),
                  ),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  child: Text(
                    conversation.getTag(),
                    style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: conversation.getTagTextColor()),
                    maxLines: 1,
                  ),
                )
              : const SizedBox.shrink(),
          const SizedBox(
            width: 16,
          ),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  dateTimeFormat('h:mm a', conversation.startedAt ?? conversation.createdAt),
                  style: const TextStyle(color: Color(0xFF6A6B71), fontSize: 14),
                  maxLines: 1,
                  textAlign: TextAlign.end,
                ),
                if (conversation.transcriptSegments.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 2.0),
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
                        textAlign: TextAlign.end,
                      ),
                    ),
                  ),
              ],
            ),
          )
        ],
      ),
    );
  }

  String _getConversationDuration() {
    if (conversation.transcriptSegments.isEmpty) return '';

    // Get the total duration in seconds
    int durationSeconds = conversation.getDurationInSeconds();
    if (durationSeconds <= 0) return '';

    return secondsToCompactDuration(durationSeconds);
  }
}
