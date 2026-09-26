import 'dart:async';
import 'dart:convert';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';

import 'package:auto_size_text/auto_size_text.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/models/chat_evidence_reference.dart';
import 'package:omi/pages/chat/widgets/chat_followup_chip.dart';
import 'package:omi/pages/chat/widgets/content_blocks/chat_content_block_list.dart';
import 'package:omi/pages/chat/widgets/files_handler_widget.dart';
import 'package:omi/pages/chat/widgets/typing_indicator.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/widgets/text_selection_controls.dart';
import 'chart_message_widget.dart';
import 'package:omi/widgets/components/chat_evidence_card.dart';
import 'package:omi/widgets/components/memory_review_card.dart';
import 'package:omi/ui/ui.dart';
import 'markdown_message_widget.dart';
import 'message_action_bar.dart';

export 'message_action_bar.dart';

/// Parse app_id from thinking text (format: "text|app_id:app_id")
String? parseAppIdFromThinking(String thinkingText) {
  if (thinkingText.contains('|app_id:')) {
    var parts = thinkingText.split('|app_id:');
    if (parts.length == 2) {
      return parts[1];
    }
  }
  return null;
}

/// Get the display text from thinking (removes app_id suffix if present)
String getThinkingDisplayText(String thinkingText) {
  int index = thinkingText.indexOf('|app_id:');
  if (index >= 0) {
    return thinkingText.substring(0, index);
  }
  return thinkingText;
}

/// Corner of the 15pt app and integration glyphs in the thinking line. The token scale starts at 8,
/// which would turn a 15pt square into a circle.
const BorderRadius _kGlyphRadius = BorderRadius.all(Radius.circular(3));

/// Build app icon widget from app_id
Widget _buildAppIcon(BuildContext context, String appId, {double size = 15, double opacity = 1.0}) {
  final appProvider = Provider.of<AppProvider>(context, listen: false);
  final messageProvider = Provider.of<MessageProvider>(context, listen: false);
  // Check both public apps and user's installed chat apps (includes private MCP apps)
  final app = appProvider.apps.firstWhereOrNull((a) => a.id == appId) ??
      messageProvider.chatApps.firstWhereOrNull((a) => a.id == appId);

  if (app != null) {
    return Opacity(
      opacity: opacity,
      child: ClipRRect(
        borderRadius: _kGlyphRadius,
        child: CachedNetworkImage(
          imageUrl: app.getImageUrl(),
          httpHeaders: const {
            "User-Agent":
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
          },
          imageBuilder: (context, imageProvider) => Container(
            width: size,
            height: size,
            decoration: BoxDecoration(
              borderRadius: _kGlyphRadius,
              image: DecorationImage(image: imageProvider, fit: BoxFit.cover),
            ),
          ),
          placeholder: (context, url) => SizedBox(
            width: size,
            height: size,
            child: Icon(
              Icons.apps,
              size: size * 0.7,
              color: Colors.white.withValues(alpha: opacity),
            ),
          ),
          errorWidget: (context, url, error) => Icon(
            Icons.apps,
            size: size * 0.7,
            color: Colors.white.withValues(alpha: opacity),
          ),
        ),
      ),
    );
  }

  // Fallback to generic icon if app not found
  return Opacity(
    opacity: opacity,
    child: Icon(
      Icons.apps,
      size: size,
      color: Colors.white.withValues(alpha: opacity),
    ),
  );
}

/// Get the integration logo path for a thinking text, if applicable
String? _getIntegrationLogoPath(String thinkingText) {
  final text = thinkingText.toLowerCase();
  if (text.contains('notion')) {
    return 'assets/integration_app_logos/notion-logo.png';
  } else if (text.contains('whoop')) {
    return 'assets/integration_app_logos/whoop.png';
  } else if (text.contains('calendar')) {
    return 'assets/integration_app_logos/google-calendar.png';
  } else if (text.contains('gmail')) {
    return 'assets/integration_app_logos/gmail-logo.jpeg';
  } else if (text.contains('github')) {
    return 'assets/integration_app_logos/github-logo.png';
  } else if (text.contains('twitter') || text.contains('tweet')) {
    return 'assets/integration_app_logos/x-logo.avif';
  }
  return null;
}

/// Get the fallback icon for thinking text (used when no integration logo)
FaIconData _getThinkingIcon(String thinkingText) {
  final text = thinkingText.toLowerCase();
  if (text.contains('thinking')) {
    return FontAwesomeIcons.brain;
  } else if (text.contains('searching the web') || text.contains('searching web')) {
    return FontAwesomeIcons.magnifyingGlass;
  } else if (text.contains('conversations')) {
    return FontAwesomeIcons.comments;
  } else if (text.contains('memories')) {
    return FontAwesomeIcons.lightbulb;
  } else if (text.contains('action item')) {
    return FontAwesomeIcons.listCheck;
  } else if (text.contains('product info')) {
    return FontAwesomeIcons.circleInfo;
  } else if (text.contains('search')) {
    return FontAwesomeIcons.magnifyingGlass;
  }
  return FontAwesomeIcons.brain; // Default brain icon
}

/// Build the thinking icon widget - either an integration logo or a fallback icon
Widget _buildThinkingIconWidget(String thinkingText, {double size = 15, Color color = Colors.white}) {
  final logoPath = _getIntegrationLogoPath(thinkingText);
  if (logoPath != null) {
    return ClipRRect(
      borderRadius: _kGlyphRadius,
      child: Image.asset(
        logoPath,
        width: size,
        height: size,
        fit: BoxFit.cover,
        errorBuilder: (context, error, stackTrace) => FaIcon(_getThinkingIcon(thinkingText), size: size, color: color),
      ),
    );
  }
  return FaIcon(_getThinkingIcon(thinkingText), size: size, color: color);
}

/// Conversation-shaped evidence is the same source list as [ServerMessage.memories].
/// Keep those citations on [MemoriesMessageWidget] only.
bool isConversationSourceEvidence(ChatEvidenceReferenceKind kind) {
  return kind == ChatEvidenceReferenceKind.conversationSummary || kind == ChatEvidenceReferenceKind.conversationSegment;
}

/// Supplemental chrome to render beside the answer. Conversation sources that
/// already appear as citation cards are stripped so the message has one list.
ChatEvidenceReferenceEnvelope? visibleSupplementalEvidence(ServerMessage message) {
  final evidence = message.evidenceEnvelope;
  if (evidence == null || evidence.isEmpty) return null;
  if (message.memories.isEmpty) return evidence;
  final leftover = evidence.references.where((ref) => !isConversationSourceEvidence(ref.kind)).toList();
  if (leftover.isEmpty) return null;
  return ChatEvidenceReferenceEnvelope(
    schemaVersion: evidence.schemaVersion,
    requestId: evidence.requestId,
    references: leftover,
  );
}

/// Resolve a cited conversation from the local grouped map, then fetch by id.
/// A miss in the map is not a failure — the fetch is the second authority.
Future<ServerConversation?> resolveChatCitationConversation({
  required ConversationProvider conversations,
  required String conversationId,
  required Future<ServerConversation?> Function(String id) fetchConversation,
}) async {
  final located = conversations.getConversationDateAndIndexById(conversationId);
  if (located != null) {
    final group = conversations.groupedConversations[located.$1];
    if (group != null && located.$2 >= 0 && located.$2 < group.length) {
      return group[located.$2];
    }
  }
  return fetchConversation(conversationId);
}

class AIMessage extends StatefulWidget {
  final bool showTypingIndicator;
  final bool showThinkingAfterText;
  final ServerMessage message;
  final Function(String) sendMessage;
  final Function(String)? onAskOmi;
  final bool displayOptions;
  final App? appSender;
  final Function(ServerConversation) updateConversation;
  final Function(int, {String? reason}) setMessageNps;
  final Future<ServerConversation?> Function(String id)? fetchConversation;

  /// The reply failed; a localized error with [onRetry] replaces the raw server text.
  final bool replyFailed;

  /// Sends the user's message again. Null when the failed reply cannot be retried (voice).
  final VoidCallback? onRetry;

  const AIMessage({
    super.key,
    required this.message,
    required this.sendMessage,
    this.onAskOmi,
    required this.displayOptions,
    required this.updateConversation,
    required this.setMessageNps,
    this.appSender,
    this.showTypingIndicator = false,
    this.showThinkingAfterText = false,
    this.fetchConversation,
    this.replyFailed = false,
    this.onRetry,
  });

  @override
  State<AIMessage> createState() => _AIMessageState();
}

class _AIMessageState extends State<AIMessage> {
  late List<bool> conversationDetailLoading;

  @override
  void initState() {
    conversationDetailLoading = List.filled(widget.message.memories.length, false);
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    if (widget.replyFailed) return ChatReplyError(onRetry: widget.onRetry);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Selection stays on markdown text only. Wrapping citation
        // GestureDetectors in SelectionArea eats taps on iOS.
        buildMessageWidget(
          widget.message,
          widget.sendMessage,
          widget.showTypingIndicator,
          widget.displayOptions,
          widget.appSender,
          widget.updateConversation,
          widget.setMessageNps,
          onAskOmi: widget.onAskOmi,
          showThinkingAfterText: widget.showThinkingAfterText,
          fetchConversation: widget.fetchConversation,
        ),
      ],
    );
  }
}

Widget buildMessageWidget(
  ServerMessage message,
  Function(String) sendMessage,
  bool showTypingIndicator,
  bool displayOptions,
  App? appSender,
  Function(ServerConversation) updateConversation,
  Function(int, {String? reason}) sendMessageNps, {
  Function(String)? onAskOmi,
  bool showThinkingAfterText = false,
  Future<ServerConversation?> Function(String id)? fetchConversation,
}) {
  final hasRenderableBlocks = ChatContentBlockList.hasRenderableBlocks(message);
  // A message whose text is only the fallback synthesized from its blocks has
  // nothing to say that the components do not already show, so the components
  // replace the body instead of repeating it. Keep this decision explicit for
  // the block list: day summaries, memory citations, and the initial-options
  // surface still render the normal body and must not render its text block a
  // second time below it.
  final blocksReplaceBody = hasRenderableBlocks &&
      message.memories.isEmpty &&
      message.type != MessageType.daySummary &&
      !displayOptions &&
      message.textIsStructuredFallback;
  final contentBlocks = hasRenderableBlocks
      ? ChatContentBlockList(
          message: message,
          sendMessage: sendMessage,
          onAskOmi: onAskOmi,
          renderStructuredFallbackText: blocksReplaceBody,
          fetchConversation: fetchConversation,
        )
      : null;

  final Widget messageWidget;
  if (blocksReplaceBody) {
    messageWidget = contentBlocks!;
  } else if (message.memories.isNotEmpty) {
    messageWidget = MemoriesMessageWidget(
      showTypingIndicator: showTypingIndicator,
      messageMemories: message.memories,
      messageText: message.isEmpty ? '…' : message.text.decodeString,
      updateConversation: updateConversation,
      message: message,
      setMessageNps: sendMessageNps,
      date: message.createdAt,
      onAskOmi: onAskOmi,
      fetchConversation: fetchConversation,
    );
  } else if (message.type == MessageType.daySummary) {
    messageWidget = DaySummaryWidget(
      showTypingIndicator: showTypingIndicator,
      messageText: message.text.decodeString,
      date: message.createdAt,
    );
  } else if (displayOptions) {
    messageWidget = InitialMessageWidget(
      showTypingIndicator: showTypingIndicator,
      messageText: message.text.decodeString,
      sendMessage: sendMessage,
      onAskOmi: onAskOmi,
    );
  } else {
    messageWidget = NormalMessageWidget(
      showTypingIndicator: showTypingIndicator,
      showThinkingAfterText: showThinkingAfterText,
      thinkings: message.thinkings,
      messageText: message.text.decodeString,
      message: message,
      setMessageNps: sendMessageNps,
      createdAt: message.createdAt,
      onAskOmi: onAskOmi,
    );
  }

  final evidence = visibleSupplementalEvidence(message);
  final appendBlocks = contentBlocks != null && !blocksReplaceBody;
  // Native content blocks. Both are additive chrome: an absent or malformed
  // block leaves the answer exactly as it renders today.
  final reviewCard = showTypingIndicator ? null : message.memoryReviewCard;
  final followUp = showTypingIndicator ? null : message.followUpQuestion;
  if (evidence == null && !appendBlocks && reviewCard == null && followUp == null) return messageWidget;
  return Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    mainAxisSize: MainAxisSize.min,
    children: [
      messageWidget,
      if (appendBlocks) ...[
        const SizedBox(height: 8),
        contentBlocks,
      ],
      if (reviewCard != null) ...[
        const SizedBox(height: 12),
        MemoryReviewCard(
          items: reviewCard.items,
          source: MemoryReviewSource.chatBlock,
          impressionKey: reviewCard.id.isNotEmpty ? reviewCard.id : message.id,
        ),
      ],
      if (evidence != null) ...[
        const SizedBox(height: 8),
        // The released mobile surface has no trusted evidence navigator yet.
        // Keep cards non-actionable until one is supplied; arbitrary URI fields
        // can never become an external action.
        ChatEvidenceReferenceList(envelope: evidence),
      ],
      if (followUp != null) ...[const SizedBox(height: 8), ChatFollowUpChip(question: followUp, onSend: sendMessage)],
    ],
  );
}

class InitialMessageWidget extends StatelessWidget {
  final bool showTypingIndicator;
  final String messageText;
  final Function(String) sendMessage;
  final Function(String)? onAskOmi;

  const InitialMessageWidget({
    super.key,
    required this.showTypingIndicator,
    required this.messageText,
    required this.sendMessage,
    this.onAskOmi,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        showTypingIndicator
            ? const Row(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.start,
                children: [SizedBox(width: 4), TypingIndicator(), Spacer()],
              )
            : getMarkdownWidget(context, messageText, onAskOmi: onAskOmi),
        const SizedBox(height: 8),
        const SizedBox(height: 8),
        InitialOptionWidget(optionText: context.l10n.chatStarterYesterday, sendMessage: sendMessage),
        const SizedBox(height: 8),
        InitialOptionWidget(optionText: context.l10n.chatStarterDoDifferently, sendMessage: sendMessage),
        const SizedBox(height: 8),
        InitialOptionWidget(optionText: context.l10n.chatStarterTeachMe, sendMessage: sendMessage),
      ],
    );
  }
}

class DaySummaryWidget extends StatelessWidget {
  final bool showTypingIndicator;
  final DateTime date;
  final String messageText;

  const DaySummaryWidget({super.key, required this.showTypingIndicator, required this.messageText, required this.date});

  @override
  Widget build(BuildContext context) {
    return Column(
      mainAxisAlignment: MainAxisAlignment.start,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Semantics(
          header: true,
          child: Text(
            context.l10n.daySummaryForDate(OmiDateFormat.of(context).date(date)),
            style: OmiType.headline.copyWith(color: OmiColors.textSecondary),
          ),
        ),
        const SizedBox(height: 16),
        showTypingIndicator
            ? const Row(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.start,
                children: [SizedBox(width: 4), TypingIndicator(), Spacer()],
              )
            : daySummaryMessagesList(messageText),
        if (messageText.isNotEmpty && !showTypingIndicator) MessageActionBar(messageText: messageText),
      ],
    );
  }

  List<String> splitMessage(String message) {
    // Check if the string contains numbered items using regex
    bool hasNumbers = RegExp(r'^\d+\.\s').hasMatch(message);

    if (hasNumbers) {
      // Remove numbers followed by period and space
      String cleanedMessage = message.replaceAll(RegExp(r'\d+\.\s'), '');
      return cleanedMessage.split(RegExp(r'\n|\.\s')).where((msg) => msg.trim().isNotEmpty).toList();
    } else {
      // Split by period followed by space
      List<String> listOfMessages = message.split('. ');
      return listOfMessages
          .map((msg) => msg.endsWith('.') ? msg.substring(0, msg.length - 1) : msg)
          .where((msg) => msg.trim().isNotEmpty)
          .toList();
    }
  }

  Widget daySummaryMessagesList(String text) {
    var sentences = splitMessage(text);

    return ListView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      itemCount: sentences.length,
      itemBuilder: (context, index) {
        return ListTile(
          visualDensity: const VisualDensity(horizontal: 0, vertical: -4),
          contentPadding: const EdgeInsets.symmetric(vertical: 2),
          horizontalTitleGap: 12,
          minLeadingWidth: 0,
          leading: Text(
            '${index + 1}.',
            style: OmiType.subhead.copyWith(fontWeight: FontWeight.bold, color: OmiColors.textTertiary),
          ),
          title: AutoSizeText(
            sentences[index],
            style: OmiType.callout.copyWith(fontWeight: FontWeight.w500, height: 1.35),
            softWrap: true,
            maxLines: 3,
            overflow: TextOverflow.ellipsis,
          ),
        );
      },
    );
  }
}

class NormalMessageWidget extends StatefulWidget {
  final bool showTypingIndicator;
  final bool showThinkingAfterText;
  final String messageText;
  final List<String> thinkings;
  final ServerMessage message;
  final Function(int, {String? reason}) setMessageNps;
  final DateTime createdAt;
  final Function(String)? onAskOmi;

  const NormalMessageWidget({
    super.key,
    required this.showTypingIndicator,
    required this.messageText,
    required this.message,
    required this.setMessageNps,
    required this.createdAt,
    this.showThinkingAfterText = false,
    this.thinkings = const [],
    this.onAskOmi,
  });

  @override
  State<NormalMessageWidget> createState() => _NormalMessageWidgetState();
}

class _NormalMessageWidgetState extends State<NormalMessageWidget> {
  bool _showDots = true;
  Timer? _dotsTimer;

  @override
  void initState() {
    super.initState();
    if (widget.showTypingIndicator && widget.messageText.isEmpty && widget.message.thinkings.isEmpty) {
      _dotsTimer = Timer(const Duration(milliseconds: 500), () {
        if (mounted) {
          setState(() {
            _showDots = false;
          });
        }
      });
    }
  }

  @override
  void dispose() {
    _dotsTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    var thinkingTextRaw = widget.message.thinkings.isNotEmpty ? widget.message.thinkings.last.decodeString : null;

    // Parse app_id and display text from thinking messages
    String? currentAppId = thinkingTextRaw != null ? parseAppIdFromThinking(thinkingTextRaw) : null;
    var thinkingText = thinkingTextRaw != null ? getThinkingDisplayText(thinkingTextRaw) : null;

    // Show "thinking" text if we have thinking text, or if dots timer expired and no thinking text yet
    bool shouldShowThinking =
        thinkingText != null || (!_showDots && widget.showTypingIndicator && widget.messageText.isEmpty);
    String displayThinkingText = thinkingText ?? context.l10n.thinking;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisAlignment: MainAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        FilesHandlerWidget(message: widget.message),
        widget.showTypingIndicator && widget.messageText.isEmpty
            ? Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    shouldShowThinking
                        ? Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisAlignment: MainAxisAlignment.start,
                              children: [
                                _ThinkingLine(text: displayThinkingText, appId: currentAppId),
                              ],
                            ),
                          )
                        : const TypingIndicator(),
                  ],
                ),
              )
            : const SizedBox.shrink(),
        // !(showTypingIndicator && messageText.isEmpty)
        //     ? Container(
        //         margin: const EdgeInsets.only(bottom: 4.0),
        //         child: Text(
        //           formatChatTimestamp(createdAt),
        //           style: TextStyle(
        //             color: Colors.grey.shade500,
        //             fontSize: 12,
        //           ),
        //         ),
        //       )
        //     : const SizedBox.shrink(),
        widget.messageText.isEmpty
            ? const SizedBox.shrink()
            : Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
                child: Builder(
                  builder: (context) {
                    String? selectedText;
                    return SelectionArea(
                      onSelectionChanged: (SelectedContent? selectedContent) {
                        selectedText = selectedContent?.plainText;
                      },
                      contextMenuBuilder: (context, selectableRegionState) {
                        return omiSelectionMenuBuilder(context, selectableRegionState, (text) {
                          widget.onAskOmi?.call(text);
                        }, selectedText: selectedText);
                      },
                      // Force full available width: SelectionArea + MarkdownBody
                      // otherwise size to the text's minimum intrinsic width, which
                      // collapses the message to ~1 word per line on iOS.
                      child: SizedBox(
                        width: double.infinity,
                        child: getMarkdownWidget(context, widget.messageText, onAskOmi: widget.onAskOmi),
                      ),
                    );
                  },
                ),
              ),
        if (widget.showTypingIndicator && widget.messageText.isNotEmpty && widget.showThinkingAfterText)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
            child: _ThinkingLine(text: displayThinkingText, appId: currentAppId),
          ),
        if (widget.message.chartData != null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: ChartMessageWidget(chartData: widget.message.chartData!),
          )
        else if (widget.showTypingIndicator && widget.message.thinkings.any((t) => t.toLowerCase().contains('chart')))
          const _ChartShimmer(),
        if (widget.messageText.isNotEmpty && !widget.showTypingIndicator)
          MessageActionBar(
            messageText: widget.messageText,
            setMessageNps: widget.setMessageNps,
            currentNps: widget.message.rating,
          ),
      ],
    );
  }
}

class MemoriesMessageWidget extends StatefulWidget {
  final bool showTypingIndicator;
  final List<MessageConversation> messageMemories;
  final String messageText;
  final Function(ServerConversation) updateConversation;
  final ServerMessage message;
  final Function(int, {String? reason}) setMessageNps;
  final DateTime date;
  final Function(String)? onAskOmi;
  final Future<ServerConversation?> Function(String id)? fetchConversation;

  const MemoriesMessageWidget({
    super.key,
    required this.showTypingIndicator,
    required this.messageMemories,
    required this.messageText,
    required this.updateConversation,
    required this.message,
    required this.setMessageNps,
    required this.date,
    this.onAskOmi,
    this.fetchConversation,
  });

  @override
  State<MemoriesMessageWidget> createState() => _MemoriesMessageWidgetState();
}

class _MemoriesMessageWidgetState extends State<MemoriesMessageWidget> {
  late List<bool> conversationDetailLoading;
  bool _showDots = true;
  Timer? _dotsTimer;

  @override
  void initState() {
    conversationDetailLoading = List.filled(widget.messageMemories.length, false);
    if (widget.showTypingIndicator && widget.messageText == '…' && widget.message.thinkings.isEmpty) {
      _dotsTimer = Timer(const Duration(milliseconds: 500), () {
        if (mounted) {
          setState(() {
            _showDots = false;
          });
        }
      });
    }
    super.initState();
  }

  @override
  void dispose() {
    _dotsTimer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    var thinkingTextRaw = widget.message.thinkings.isNotEmpty ? widget.message.thinkings.last.decodeString : null;

    // Parse app_id and display text from thinking messages
    String? currentAppId = thinkingTextRaw != null ? parseAppIdFromThinking(thinkingTextRaw) : null;
    var thinkingText = thinkingTextRaw != null ? getThinkingDisplayText(thinkingTextRaw) : null;

    // Show "thinking" text if we have thinking text, or if dots timer expired and no thinking text yet
    bool shouldShowThinking =
        thinkingText != null || (!_showDots && widget.showTypingIndicator && widget.messageText == '…');
    String displayThinkingText = thinkingText ?? context.l10n.thinking;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Padding(
        //   padding: const EdgeInsets.only(bottom: 4.0),
        //   child: Text(
        //     formatChatTimestamp(widget.date),
        //     style: TextStyle(
        //       color: Colors.grey.shade500,
        //       fontSize: 12,
        //     ),
        //   ),
        // ),
        widget.showTypingIndicator && widget.messageText == '…'
            ? Padding(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    shouldShowThinking
                        ? Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisAlignment: MainAxisAlignment.start,
                              children: [
                                _ThinkingLine(text: displayThinkingText, appId: currentAppId),
                              ],
                            ),
                          )
                        : const TypingIndicator(),
                  ],
                ),
              )
            : widget.showTypingIndicator
                ? const Row(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.start,
                    children: [SizedBox(width: 4), TypingIndicator(), Spacer()],
                  )
                : Builder(
                    builder: (context) {
                      String? selectedText;
                      return SelectionArea(
                        onSelectionChanged: (SelectedContent? selectedContent) {
                          selectedText = selectedContent?.plainText;
                        },
                        contextMenuBuilder: (context, selectableRegionState) {
                          return omiSelectionMenuBuilder(context, selectableRegionState, (text) {
                            widget.onAskOmi?.call(text);
                          }, selectedText: selectedText);
                        },
                        child: getMarkdownWidget(context, widget.messageText, onAskOmi: widget.onAskOmi),
                      );
                    },
                  ),
        if (widget.messageText.isNotEmpty && widget.messageText != '…' && !widget.showTypingIndicator)
          MessageActionBar(
            messageText: widget.messageText,
            setMessageNps: widget.setMessageNps,
            currentNps: widget.message.rating,
          ),
        if (widget.message.chartData != null)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: ChartMessageWidget(chartData: widget.message.chartData!),
          )
        else if (widget.showTypingIndicator && widget.message.thinkings.any((t) => t.toLowerCase().contains('chart')))
          const _ChartShimmer(),
        const SizedBox(height: 16),
        Column(
          key: const ValueKey('chat-citation-list'),
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            for (var data in widget.messageMemories.indexed)
              Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(0.0, 4.0, 0.0, 4.0),
                child: GestureDetector(
                  key: ValueKey('chat-citation-${data.$2.id}'),
                  onTap: () => _openCitedConversation(data.$1, data.$2),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16.0, vertical: 12),
                    width: double.maxFinite,
                    decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            '${tryDecodeText(data.$2.structured.emoji)} ${data.$2.structured.title}',
                            style: Theme.of(context).textTheme.bodyMedium,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        const SizedBox(width: 8),
                        conversationDetailLoading[data.$1]
                            ? const OmiSpinner(size: OmiSpinnerSize.small, color: OmiColors.textSecondary)
                            : const FaIcon(FontAwesomeIcons.chevronRight, size: 16, color: OmiColors.textTertiary),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      ],
    );
  }

  Future<void> _openCitedConversation(int index, MessageConversation citation) async {
    final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
    if (!connectivityProvider.isConnected) {
      OmiFeedback.error(context, context.l10n.pleaseCheckInternetConnection);
      return;
    }

    final memProvider = Provider.of<ConversationProvider>(context, listen: false);
    final fetch = widget.fetchConversation ?? getConversationById;
    ServerConversation? conversation = await resolveChatCitationConversation(
      conversations: memProvider,
      conversationId: citation.id,
      fetchConversation: (id) async {
        if (conversationDetailLoading[index]) return null;
        setState(() => conversationDetailLoading[index] = true);
        try {
          return await fetch(id);
        } finally {
          if (mounted) setState(() => conversationDetailLoading[index] = false);
        }
      },
    );

    if (!mounted) return;
    if (conversation == null) {
      OmiFeedback.info(context, context.l10n.conversationNotFoundOrDeleted);
      return;
    }

    var located = memProvider.getConversationDateAndIndexById(conversation.id);
    var date = located?.$1;
    if (date == null) {
      (_, date) = memProvider.addConversationWithDateGrouped(conversation);
    }

    PlatformManager.instance.analytics.chatMessageConversationClicked(conversation);
    if (!context.mounted) return;
    context.read<ConversationDetailProvider>().updateConversation(conversation.id, date);
    await routeToPage(context, ConversationDetailPage(conversation: conversation));

    if (SharedPreferencesUtil().modifiedConversationDetails?.id == conversation.id) {
      final modifiedDetails = SharedPreferencesUtil().modifiedConversationDetails!;
      widget.updateConversation(modifiedDetails);
      final copy = List<MessageConversation>.from(widget.messageMemories);
      copy[index] = MessageConversation(
        modifiedDetails.id,
        modifiedDetails.createdAt,
        MessageConversationStructured(modifiedDetails.structured.title, modifiedDetails.structured.emoji),
      );
      widget.messageMemories.clear();
      widget.messageMemories.addAll(copy);
      SharedPreferencesUtil().modifiedConversationDetails = null;
      if (mounted) setState(() {});
    }
  }

  String tryDecodeText(String text) {
    try {
      return utf8.decode(text.codeUnits);
    } catch (e) {
      return text;
    }
  }
}

/// The app icon or integration logo, then the shimmering "thinking" text, while a reply streams.
class _ThinkingLine extends StatelessWidget {
  const _ThinkingLine({required this.text, this.appId});

  final String text;
  final String? appId;

  @override
  Widget build(BuildContext context) {
    final appId = this.appId;
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        // The icon stays outside the shimmer so an app icon or integration logo keeps its colours.
        if (appId != null) _buildAppIcon(context, appId, size: 15) else _buildThinkingIconWidget(text, size: 15),
        const SizedBox(width: 6),
        Flexible(
          child: ShimmerWithTimeout(
            baseColor: OmiColors.textPrimary,
            highlightColor: OmiColors.textTertiary,
            child: Text(text, overflow: TextOverflow.fade, maxLines: 1, softWrap: false, style: OmiType.subhead),
          ),
        ),
      ],
    );
  }
}

/// Placeholder where a chart will appear while the reply that draws it is still streaming.
class _ChartShimmer extends StatelessWidget {
  const _ChartShimmer();

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 8),
      child: ShimmerWithTimeout(
        baseColor: OmiColors.surface1,
        highlightColor: OmiColors.surface2,
        timeoutSeconds: 15,
        child: Container(
          height: 236,
          decoration: BoxDecoration(
            color: OmiColors.surface1,
            borderRadius: OmiRadius.lgAll,
            border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
          ),
        ),
      ),
    );
  }
}

class InitialOptionWidget extends StatelessWidget {
  final String optionText;
  final Function(String) sendMessage;

  const InitialOptionWidget({super.key, required this.optionText, required this.sendMessage});

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      child: GestureDetector(
        child: Container(
          constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
          padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 10),
          width: double.maxFinite,
          decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
          child: Text(optionText, style: Theme.of(context).textTheme.bodyMedium),
        ),
        onTap: () {
          sendMessage(optionText);
        },
      ),
    );
  }
}

/// A reply that failed: a localized reason and Try Again, which sends the user's message again.
class ChatReplyError extends StatelessWidget {
  const ChatReplyError({super.key, this.onRetry});

  /// Null when the message cannot be sent again from here (a voice message).
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    return Semantics(
      liveRegion: true,
      child: Container(
        padding: const EdgeInsets.all(OmiSpacing.sm),
        decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.mdAll),
        child: Row(
          children: [
            const ExcludeSemantics(child: Icon(Icons.error_outline_rounded, size: 20, color: OmiColors.danger)),
            const SizedBox(width: OmiSpacing.sm),
            Expanded(
              child: Text(l10n.chatReplyFailed, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
            ),
            if (onRetry != null)
              Padding(
                padding: const EdgeInsets.only(left: OmiSpacing.xs),
                child: OmiButton.secondary(label: l10n.tryAgain, size: OmiButtonSize.compact, onPressed: onRetry),
              ),
          ],
        ),
      ),
    );
  }
}
