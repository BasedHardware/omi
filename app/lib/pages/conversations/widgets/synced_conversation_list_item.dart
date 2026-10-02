import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

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

    final raw = conversation.discarded
        ? (conversation.transcriptSegments.isEmpty ? '' : conversation.transcriptSegments.first.text.decodeString)
        : conversation.structured.title.decodeString;
    final title = raw.trim().isEmpty ? context.l10n.untitledConversation : raw;
    final time = OmiDateFormat.of(context).time(conversation.startedAt ?? conversation.createdAt);
    final duration = _getConversationDuration(context);
    // The category a processed conversation was filed under, ahead of its time.
    final tag = !conversation.discarded && conversation.structured.category.isNotEmpty ? conversation.getTag() : '';
    final subtitle = [tag, time, duration].where((part) => part.isNotEmpty).join(' \u00b7 ');

    return OmiSettingsGroup(
      children: [
        OmiSettingsRow(
          leading: OmiSettingsIconTile.custom(
            child: conversation.discarded
                ? const OmiLineIcon(OmiLineGlyph.wave)
                : Text(conversation.structured.getEmoji(), style: OmiType.title3),
          ),
          title: title,
          subtitle: subtitle,
          trailing: widget.showReprocess || conversation.discarded
              ? (isReprocessing
                  ? const Padding(padding: EdgeInsets.all(OmiSpacing.sm), child: OmiSpinner(size: OmiSpinnerSize.small))
                  : OmiIconButton(
                      icon: const OmiLineIcon(OmiLineGlyph.refresh),
                      label: context.l10n.reprocessConversation,
                      color: OmiColors.textSecondary,
                      onPressed: () async {
                        setReprocessing(true);
                        var mem = await reProcessConversationServer(conversation.id);
                        if (!context.mounted) return;
                        if (mem != null) {
                          setState(() {
                            conversation = mem;
                          });
                          context.read<ConversationProvider>().updateSyncedConversation(mem);
                        }
                        setReprocessing(false);
                      },
                    ))
              : null,
          onTap: () async {
            context.read<ConversationDetailProvider>().updateConversation(widget.conversation.id, widget.date);
            Provider.of<ConversationProvider>(context, listen: false).onConversationTap(widget.conversation.id);
            routeToPage(context, ConversationDetailPage(conversation: widget.conversation, isFromOnboarding: false));
          },
        ),
      ],
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
