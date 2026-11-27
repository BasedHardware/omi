import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/services/experiments/experimental_design.dart';
import 'package:omi/utils/conversations/conversation_title.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/widgets/extensions/string.dart';

class SyncedConversationListItem extends StatefulWidget {
  final DateTime date;
  final int conversationIdx;
  final ServerConversation conversation;
  final bool showReprocess;

  /// Optional reprocess override for tests.
  final Future<ReprocessResult> Function(String conversationId)? reprocess;

  const SyncedConversationListItem({
    super.key,
    required this.conversation,
    required this.date,
    required this.conversationIdx,
    this.showReprocess = false,
    this.reprocess,
  });

  @override
  State<SyncedConversationListItem> createState() => _SyncedConversationListItemState();
}

class _SyncedConversationListItemState extends State<SyncedConversationListItem> {
  bool isReprocessing = false;
  late ServerConversation conversation;

  void setReprocessing(bool value) {
    isReprocessing = value;
    if (mounted) setState(() {});
  }

  @override
  void initState() {
    super.initState();
    conversation = widget.conversation;
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
        Provider.of<ConversationProvider>(context, listen: false).onConversationTap(widget.conversation.id);
        routeToPage(context, ConversationDetailPage(conversation: widget.conversation, isFromOnboarding: false));
      },
      child: Padding(
        padding: const EdgeInsets.only(top: 12, left: 16, right: 16),
        child: Container(
          width: double.maxFinite,
          decoration: BoxDecoration(
              color: ExperimentalDesign.of(context) ? Colors.transparent : OmiColors.conversationCard,
              borderRadius: BorderRadius.circular(24.0)),
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
                              presentableConversationTitleOrFallback(conversation, context.l10n),
                              style: Theme.of(context).textTheme.titleLarge,
                              maxLines: 1,
                            ),
                      conversation.discarded ? const SizedBox.shrink() : const SizedBox(height: 8),
                    ],
                  ),
                ),
                widget.showReprocess || conversation.discarded
                    ? GestureDetector(
                        onTap: () => _reprocess(context),
                        child: isReprocessing
                            ? const Center(
                                child: Padding(
                                    padding: EdgeInsets.all(8.0), child: OmiSpinner(size: OmiSpinnerSize.small)),
                              )
                            : Padding(
                                padding: const EdgeInsets.all(8.0),
                                child: Icon(Icons.refresh_outlined, color: OmiColors.textTertiary),
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

  Future<void> _reprocess(BuildContext context) async {
    if (isReprocessing) return;
    setReprocessing(true);
    try {
      final result = await (widget.reprocess ?? reProcessConversationServer)(conversation.id);
      if (!context.mounted) return;
      // A still-transcribing copy is the server's own waiting state: show it like a result.
      final updated = result.conversation;
      if (updated != null) {
        setState(() => conversation = updated);
        context.read<ConversationProvider>().updateSyncedConversation(updated);
      }
      switch (result) {
        case ReprocessSuccess():
          break;
        case ReprocessTranscriptionPending():
          OmiFeedback.info(context, context.l10n.summaryTranscriptionPendingBody);
        case ReprocessBusy():
          OmiFeedback.info(context, context.l10n.summaryBusyBody);
        case ReprocessRateLimited():
          OmiFeedback.info(context, context.l10n.summaryLimitBody);
        default:
          OmiFeedback.error(context, context.l10n.somethingWentWrong);
      }
    } catch (_) {
      if (context.mounted) OmiFeedback.error(context, context.l10n.somethingWentWrong);
    } finally {
      setReprocessing(false);
    }
  }

  _getConversationHeader() {
    return Padding(
      padding: const EdgeInsets.only(left: 4.0, right: 12),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          conversation.discarded
              ? const SizedBox.shrink()
              : Text(
                  conversation.structured.getEmoji(),
                  style: TextStyle(color: OmiColors.textPrimary, fontSize: 22, fontWeight: FontWeight.w500),
                ),
          conversation.structured.category.isNotEmpty && !conversation.discarded
              ? const SizedBox(width: 12)
              : const SizedBox.shrink(),
          conversation.structured.category.isNotEmpty
              ? Container(
                  decoration: BoxDecoration(color: conversation.getTagColor(), borderRadius: BorderRadius.circular(16)),
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  child: Text(
                    conversation.getTag(),
                    style: Theme.of(context).textTheme.bodyMedium!.copyWith(color: conversation.getTagTextColor()),
                    maxLines: 1,
                  ),
                )
              : const SizedBox.shrink(),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text(
                  OmiDateFormat.of(context).time(conversation.startedAt ?? conversation.createdAt),
                  style: const TextStyle(color: Color(0xFF6A6B71), fontSize: 14),
                  maxLines: 1,
                  textAlign: TextAlign.end,
                ),
                if (conversation.transcriptSegments.isNotEmpty)
                  Padding(
                    padding: const EdgeInsets.only(top: 2.0),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration:
                          BoxDecoration(color: OmiColors.categorySurface, borderRadius: BorderRadius.circular(4)),
                      child: Text(
                        _getConversationDuration(context),
                        style: TextStyle(color: OmiColors.textPrimary, fontSize: 11),
                        maxLines: 1,
                        textAlign: TextAlign.end,
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

  String _getConversationDuration(BuildContext context) {
    if (conversation.transcriptSegments.isEmpty) return '';

    // Get the total duration in seconds
    int durationSeconds = conversation.getDurationInSeconds();
    if (durationSeconds <= 0) return '';

    return OmiDuration.compact(durationSeconds, context.l10n);
  }
}
