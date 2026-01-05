import 'dart:async';
import 'dart:convert';

import 'package:auto_size_text/auto_size_text.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/pages/chat/widgets/files_handler_widget.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/pages/chat/widgets/typing_indicator.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:shimmer/shimmer.dart';

import 'markdown_message_widget.dart';
import 'package:omi/widgets/text_selection_controls.dart';
import 'package:omi/providers/app_provider.dart';

/// Parse app_id from thinking text (format: "text|app_id:app_id")
String? _parseAppIdFromThinking(String thinkingText) {
  if (thinkingText.contains('|app_id:')) {
    var parts = thinkingText.split('|app_id:');
    if (parts.length == 2) {
      return parts[1];
    }
  }
  return null;
}

/// Get the display text from thinking (removes app_id suffix if present)
String _getThinkingDisplayText(String thinkingText) {
  if (thinkingText.contains('|app_id:')) {
    var parts = thinkingText.split('|app_id:');
    if (parts.length == 2) {
      return parts[0];
    }
  }
  return thinkingText;
}

/// Build app icon widget from app_id
Widget _buildAppIcon(BuildContext context, String appId, {double size = 15, double opacity = 1.0}) {
  final appProvider = Provider.of<AppProvider>(context, listen: false);
  final app = appProvider.apps.firstWhereOrNull((a) => a.id == appId);

  if (app != null) {
    return Opacity(
      opacity: opacity,
      child: ClipRRect(
        borderRadius: BorderRadius.circular(3),
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
              borderRadius: BorderRadius.circular(3),
              image: DecorationImage(
                image: imageProvider,
                fit: BoxFit.cover,
              ),
            ),
          ),
          placeholder: (context, url) => SizedBox(
            width: size,
            height: size,
            child: Icon(
              Icons.apps,
              size: size * 0.7,
              color: Colors.white.withOpacity(opacity),
            ),
          ),
          errorWidget: (context, url, error) => Icon(
            Icons.apps,
            size: size * 0.7,
            color: Colors.white.withOpacity(opacity),
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
      color: Colors.white.withOpacity(opacity),
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
IconData _getThinkingIcon(String thinkingText) {
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
      borderRadius: BorderRadius.circular(3),
      child: Image.asset(
        logoPath,
        width: size,
        height: size,
        fit: BoxFit.cover,
        errorBuilder: (context, error, stackTrace) => FaIcon(
          _getThinkingIcon(thinkingText),
          size: size,
          color: color,
        ),
      ),
    );
  }
  return FaIcon(
    _getThinkingIcon(thinkingText),
    size: size,
    color: color,
  );
}

class AIMessage extends StatefulWidget {
  final bool showTypingIndicator;
  final ServerMessage message;
  final Function(String) sendMessage;
  final Function(String)? onAskOmi;
  final bool displayOptions;
  final App? appSender;
  final Function(ServerConversation) updateConversation;
  final Function(int) setMessageNps;

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
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SelectionArea(
          contextMenuBuilder: (context, selectableRegionState) {
            return omiSelectionMenuBuilder(context, selectableRegionState, widget.onAskOmi ?? (text) {});
          },
          child: buildMessageWidget(
            widget.message,
            widget.sendMessage,
            widget.showTypingIndicator,
            widget.displayOptions,
            widget.appSender,
            widget.updateConversation,
            widget.setMessageNps,
            onAskOmi: widget.onAskOmi,
          ),
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
  Function(int) sendMessageNps, {
  Function(String)? onAskOmi,
}) {
  if (message.memories.isNotEmpty) {
    return MemoriesMessageWidget(
        showTypingIndicator: showTypingIndicator,
        messageMemories: message.memories.length > 3 ? message.memories.sublist(0, 3) : message.memories,
        messageText: message.isEmpty ? '...' : message.text.decodeString,
        updateConversation: updateConversation,
        message: message,
        setMessageNps: sendMessageNps,
        date: message.createdAt,
        onAskOmi: onAskOmi);
  } else if (message.type == MessageType.daySummary) {
    return DaySummaryWidget(
        showTypingIndicator: showTypingIndicator, messageText: message.text.decodeString, date: message.createdAt);
  } else if (displayOptions) {
    return InitialMessageWidget(
      showTypingIndicator: showTypingIndicator,
      messageText: message.text.decodeString,
      sendMessage: sendMessage,
      onAskOmi: onAskOmi,
    );
  } else {
    return NormalMessageWidget(
      showTypingIndicator: showTypingIndicator,
      thinkings: message.thinkings,
      messageText: message.text.decodeString,
      message: message,
      setMessageNps: sendMessageNps,
      createdAt: message.createdAt,
      onAskOmi: onAskOmi,
    );
  }
}

class InitialMessageWidget extends StatelessWidget {
  final bool showTypingIndicator;
  final String messageText;
  final Function(String) sendMessage;
  final Function(String)? onAskOmi;

  const InitialMessageWidget(
      {super.key,
      required this.showTypingIndicator,
      required this.messageText,
      required this.sendMessage,
      this.onAskOmi});

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        showTypingIndicator
            ? const Row(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.start,
                children: [
                  SizedBox(width: 4),
                  TypingIndicator(),
                  Spacer(),
                ],
              )
            : getMarkdownWidget(context, messageText, onAskOmi: onAskOmi),
        const SizedBox(height: 8),
        const SizedBox(height: 8),
        InitialOptionWidget(optionText: 'What did I do yesterday?', sendMessage: sendMessage),
        const SizedBox(height: 8),
        InitialOptionWidget(optionText: 'What could I do differently today?', sendMessage: sendMessage),
        const SizedBox(height: 8),
        InitialOptionWidget(optionText: 'Can you teach me something new?', sendMessage: sendMessage),
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
        Text(
          '📅  Day Summary ~ ${dateTimeFormat('MMM, dd', date)}',
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.w500,
            color: Colors.grey.shade300,
            decoration: TextDecoration.underline,
          ),
        ),
        const SizedBox(height: 16),
        showTypingIndicator
            ? const Row(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisAlignment: MainAxisAlignment.start,
                children: [
                  SizedBox(width: 4),
                  TypingIndicator(),
                  Spacer(),
                ],
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
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.bold,
              color: Colors.grey.shade500,
            ),
          ),
          title: AutoSizeText(
            sentences[index],
            style: const TextStyle(
              fontSize: 16.0,
              fontWeight: FontWeight.w500,
              height: 1.35,
              color: Colors.white,
            ),
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
  final String messageText;
  final List<String> thinkings;
  final ServerMessage message;
  final Function(int) setMessageNps;
  final DateTime createdAt;
  final Function(String)? onAskOmi;

  const NormalMessageWidget({
    super.key,
    required this.showTypingIndicator,
    required this.messageText,
    required this.message,
    required this.setMessageNps,
    required this.createdAt,
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
    var previousThinkingTextRaw = widget.message.thinkings.length > 1
        ? widget.message.thinkings
            .sublist(widget.message.thinkings.length - 2 >= 0 ? widget.message.thinkings.length - 2 : 0)
            .first
            .decodeString
        : null;
    var thinkingTextRaw = widget.message.thinkings.isNotEmpty ? widget.message.thinkings.last.decodeString : null;

    // Parse app_id and display text from thinking messages
    String? previousAppId = previousThinkingTextRaw != null ? _parseAppIdFromThinking(previousThinkingTextRaw) : null;
    String? currentAppId = thinkingTextRaw != null ? _parseAppIdFromThinking(thinkingTextRaw) : null;
    String? previousThinkingText =
        previousThinkingTextRaw != null ? _getThinkingDisplayText(previousThinkingTextRaw) : null;
    var thinkingText = thinkingTextRaw != null ? _getThinkingDisplayText(thinkingTextRaw) : null;

    // Show "thinking" text if we have thinking text, or if dots timer expired and no thinking text yet
    bool shouldShowThinking =
        thinkingText != null || (!_showDots && widget.showTypingIndicator && widget.messageText.isEmpty);
    String displayThinkingText = thinkingText ?? 'Thinking';

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
                                previousThinkingText != null
                                    ? Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          previousAppId != null
                                              ? _buildAppIcon(context, previousAppId, size: 15, opacity: 0.6)
                                              : Opacity(
                                                  opacity: 0.6,
                                                  child: _buildThinkingIconWidget(previousThinkingText,
                                                      size: 15, color: Colors.white),
                                                ),
                                          const SizedBox(width: 6),
                                          Flexible(
                                            child: Text(
                                              overflow: TextOverflow.fade,
                                              maxLines: 1,
                                              softWrap: false,
                                              previousThinkingText,
                                              style: const TextStyle(color: Colors.white60, fontSize: 15),
                                            ),
                                          ),
                                        ],
                                      )
                                    : const SizedBox.shrink(),
                                Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    // Icon stays outside shimmer to preserve colors (app icon or integration logo)
                                    if (currentAppId != null) ...[
                                      _buildAppIcon(context, currentAppId, size: 15),
                                      const SizedBox(width: 6),
                                    ] else ...[
                                      _buildThinkingIconWidget(displayThinkingText, size: 15),
                                      const SizedBox(width: 6),
                                    ],
                                    // Shimmer only applies to text
                                    Flexible(
                                      child: Shimmer.fromColors(
                                        baseColor: Colors.white,
                                        highlightColor: Colors.grey,
                                        child: Text(
                                          overflow: TextOverflow.fade,
                                          maxLines: 1,
                                          softWrap: false,
                                          displayThinkingText,
                                          style: const TextStyle(color: Colors.white, fontSize: 15),
                                        ),
                                      ),
                                    ),
                                  ],
                                )
                              ],
                            ),
                          )
                        : const TypingIndicator(),
                  ],
                ))
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
                        return omiSelectionMenuBuilder(
                          context,
                          selectableRegionState,
                          (text) {
                            widget.onAskOmi?.call(text);
                          },
                          selectedText: selectedText,
                        );
                      },
                      child: getMarkdownWidget(context, widget.messageText, onAskOmi: widget.onAskOmi),
                    );
                  },
                ),
              ),
        if (widget.messageText.isNotEmpty && !widget.showTypingIndicator)
          MessageActionBar(
            messageText: widget.messageText,
            setMessageNps: widget.setMessageNps,
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
  final Function(int) setMessageNps;
  final DateTime date;
  final Function(String)? onAskOmi;

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
    if (widget.showTypingIndicator && widget.messageText == '...' && widget.message.thinkings.isEmpty) {
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
    var previousThinkingTextRaw = widget.message.thinkings.length > 1
        ? widget.message.thinkings
            .sublist(widget.message.thinkings.length - 2 >= 0 ? widget.message.thinkings.length - 2 : 0)
            .first
            .decodeString
        : null;
    var thinkingTextRaw = widget.message.thinkings.isNotEmpty ? widget.message.thinkings.last.decodeString : null;

    // Parse app_id and display text from thinking messages
    String? previousAppId = previousThinkingTextRaw != null ? _parseAppIdFromThinking(previousThinkingTextRaw) : null;
    String? currentAppId = thinkingTextRaw != null ? _parseAppIdFromThinking(thinkingTextRaw) : null;
    String? previousThinkingText =
        previousThinkingTextRaw != null ? _getThinkingDisplayText(previousThinkingTextRaw) : null;
    var thinkingText = thinkingTextRaw != null ? _getThinkingDisplayText(thinkingTextRaw) : null;

    // Show "thinking" text if we have thinking text, or if dots timer expired and no thinking text yet
    bool shouldShowThinking =
        thinkingText != null || (!_showDots && widget.showTypingIndicator && widget.messageText == '...');
    String displayThinkingText = thinkingText ?? 'Thinking';

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
        widget.showTypingIndicator && widget.messageText == '...'
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
                                previousThinkingText != null
                                    ? Row(
                                        mainAxisSize: MainAxisSize.min,
                                        children: [
                                          previousAppId != null
                                              ? _buildAppIcon(context, previousAppId, size: 15, opacity: 0.6)
                                              : Opacity(
                                                  opacity: 0.6,
                                                  child: _buildThinkingIconWidget(previousThinkingText,
                                                      size: 15, color: Colors.white),
                                                ),
                                          const SizedBox(width: 6),
                                          Flexible(
                                            child: Text(
                                              overflow: TextOverflow.fade,
                                              maxLines: 1,
                                              softWrap: false,
                                              previousThinkingText,
                                              style: const TextStyle(color: Colors.white60, fontSize: 15),
                                            ),
                                          ),
                                        ],
                                      )
                                    : const SizedBox.shrink(),
                                Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    // Icon stays outside shimmer to preserve colors (app icon or integration logo)
                                    if (currentAppId != null) ...[
                                      _buildAppIcon(context, currentAppId, size: 15),
                                      const SizedBox(width: 6),
                                    ] else ...[
                                      _buildThinkingIconWidget(displayThinkingText, size: 15),
                                      const SizedBox(width: 6),
                                    ],
                                    // Shimmer only applies to text
                                    Flexible(
                                      child: Shimmer.fromColors(
                                        baseColor: Colors.white,
                                        highlightColor: Colors.grey,
                                        child: Text(
                                          overflow: TextOverflow.fade,
                                          maxLines: 1,
                                          softWrap: false,
                                          displayThinkingText,
                                          style: const TextStyle(color: Colors.white, fontSize: 15),
                                        ),
                                      ),
                                    ),
                                  ],
                                )
                              ],
                            ),
                          )
                        : const TypingIndicator(),
                  ],
                ))
            : widget.showTypingIndicator
                ? const Row(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisAlignment: MainAxisAlignment.start,
                    children: [
                      SizedBox(width: 4),
                      TypingIndicator(),
                      Spacer(),
                    ],
                  )
                : Builder(
                    builder: (context) {
                      String? selectedText;
                      return SelectionArea(
                        onSelectionChanged: (SelectedContent? selectedContent) {
                          selectedText = selectedContent?.plainText;
                        },
                        contextMenuBuilder: (context, selectableRegionState) {
                          return omiSelectionMenuBuilder(
                            context,
                            selectableRegionState,
                            (text) {
                              widget.onAskOmi?.call(text);
                            },
                            selectedText: selectedText,
                          );
                        },
                        child: getMarkdownWidget(context, widget.messageText, onAskOmi: widget.onAskOmi),
                      );
                    },
                  ),
        if (widget.messageText.isNotEmpty && widget.messageText != '...' && !widget.showTypingIndicator)
          MessageActionBar(
            messageText: widget.messageText,
            setMessageNps: widget.setMessageNps,
          ),
        const SizedBox(height: 16),
        for (var data in widget.messageMemories.indexed) ...[
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 4.0),
            child: GestureDetector(
              onTap: () async {
                final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                if (connectivityProvider.isConnected) {
                  var memProvider = Provider.of<ConversationProvider>(context, listen: false);
                  var idx = -1;
                  var date = DateTime(data.$2.createdAt.year, data.$2.createdAt.month, data.$2.createdAt.day);
                  idx = memProvider.groupedConversations[date]?.indexWhere((element) => element.id == data.$2.id) ?? -1;

                  if (idx != -1) {
                    context.read<ConversationDetailProvider>().updateConversation(data.$2.id, date);
                    var m = memProvider.groupedConversations[date]![idx];
                    MixpanelManager().chatMessageConversationClicked(m);
                    await Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (c) => ConversationDetailPage(
                          conversation: m,
                        ),
                      ),
                    );
                  } else {
                    if (conversationDetailLoading[data.$1]) return;
                    setState(() => conversationDetailLoading[data.$1] = true);
                    ServerConversation? m = await getConversationById(data.$2.id);
                    if (m == null) return;
                    (idx, date) = memProvider.addConversationWithDateGrouped(m);
                    MixpanelManager().chatMessageConversationClicked(m);
                    setState(() => conversationDetailLoading[data.$1] = false);
                    context.read<ConversationDetailProvider>().updateConversation(m.id, date);
                    await Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (c) => ConversationDetailPage(
                          conversation: m,
                        ),
                      ),
                    );
                    if (SharedPreferencesUtil().modifiedConversationDetails?.id == m.id) {
                      ServerConversation modifiedDetails = SharedPreferencesUtil().modifiedConversationDetails!;
                      widget.updateConversation(SharedPreferencesUtil().modifiedConversationDetails!);
                      var copy = List<MessageConversation>.from(widget.messageMemories);
                      copy[data.$1] = MessageConversation(
                          modifiedDetails.id,
                          modifiedDetails.createdAt,
                          MessageConversationStructured(
                            modifiedDetails.structured.title,
                            modifiedDetails.structured.emoji,
                          ));
                      widget.messageMemories.clear();
                      widget.messageMemories.addAll(copy);
                      SharedPreferencesUtil().modifiedConversationDetails = null;
                      setState(() {});
                    }
                  }
                } else {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text('Please check your internet connection and try again'),
                      duration: Duration(seconds: 2),
                    ),
                  );
                }
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 8),
                width: double.maxFinite,
                decoration: BoxDecoration(
                  color: const Color(0xFF1F1F25),
                  borderRadius: BorderRadius.circular(12.0),
                ),
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
                        ? const SizedBox(
                            height: 24,
                            width: 24,
                            child: CircularProgressIndicator(
                              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                            ))
                        : const Icon(Icons.arrow_right_alt)
                  ],
                ),
              ),
            ),
          ),
        ],
      ],
    );
  }

  String tryDecodeText(String text) {
    try {
      return utf8.decode(text.codeUnits);
    } catch (e) {
      return text;
    }
  }
}

class MessageActionBar extends StatefulWidget {
  final String messageText;
  final Function(int)? setMessageNps;
  final int? currentNps;

  const MessageActionBar({
    super.key,
    required this.messageText,
    this.setMessageNps,
    this.currentNps,
  });

  @override
  State<MessageActionBar> createState() => _MessageActionBarState();
}

class _MessageActionBarState extends State<MessageActionBar> {
  int? _selectedNps;

  @override
  void initState() {
    super.initState();
    _selectedNps = widget.currentNps;
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 2, left: 4),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          // Copy button
          _buildActionButton(
            icon: FontAwesomeIcons.copy,
            onTap: () async {
              HapticFeedback.lightImpact();
              await Clipboard.setData(ClipboardData(text: widget.messageText));
              if (context.mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(
                      context.l10n.messageCopied,
                      style: TextStyle(color: Colors.white, fontSize: 12.0),
                    ),
                    duration: Duration(milliseconds: 1500),
                  ),
                );
              }
            },
          ),
          const SizedBox(width: 20),
          // Thumbs up button
          _buildActionButton(
            icon: _selectedNps == 1 ? FontAwesomeIcons.solidThumbsUp : FontAwesomeIcons.thumbsUp,
            isSelected: _selectedNps == 1,
            onTap: () {
              HapticFeedback.lightImpact();
              setState(() {
                _selectedNps = _selectedNps == 1 ? null : 1;
              });
              widget.setMessageNps?.call(_selectedNps ?? 0);
            },
          ),
          const SizedBox(width: 20),
          // Thumbs down button
          _buildActionButton(
            icon: _selectedNps == -1 ? FontAwesomeIcons.solidThumbsDown : FontAwesomeIcons.thumbsDown,
            isSelected: _selectedNps == -1,
            onTap: () {
              HapticFeedback.lightImpact();
              setState(() {
                _selectedNps = _selectedNps == -1 ? null : -1;
              });
              widget.setMessageNps?.call(_selectedNps ?? 0);
            },
          ),
          const SizedBox(width: 20),
          // Share button
          _buildActionButton(
            icon: FontAwesomeIcons.shareNodes,
            onTap: () async {
              HapticFeedback.lightImpact();
              await Share.share(widget.messageText);
            },
          ),
        ],
      ),
    );
  }

  Widget _buildActionButton({
    required IconData icon,
    required VoidCallback onTap,
    bool isSelected = false,
  }) {
    return InkWell(
      splashColor: Colors.transparent,
      focusColor: Colors.transparent,
      hoverColor: Colors.transparent,
      highlightColor: Colors.transparent,
      onTap: onTap,
      child: FaIcon(
        icon,
        color: isSelected ? Colors.white : Colors.grey.shade600,
        size: 16,
      ),
    );
  }
}

class CopyButton extends StatelessWidget {
  final String messageText;
  final bool isUserMessage;

  const CopyButton({
    super.key,
    required this.messageText,
    this.isUserMessage = false,
  });

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(0.0, 8, 0.0, 0.0),
      child: InkWell(
        splashColor: Colors.transparent,
        focusColor: Colors.transparent,
        hoverColor: Colors.transparent,
        highlightColor: Colors.transparent,
        onTap: () async {
          await Clipboard.setData(ClipboardData(text: messageText));
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text(
                'Message copied to clipboard.',
                style: TextStyle(
                  color: Color.fromARGB(255, 255, 255, 255),
                  fontSize: 12.0,
                ),
              ),
              duration: Duration(milliseconds: 2000),
            ),
          );
        },
        child: Row(
          mainAxisSize: MainAxisSize.max,
          mainAxisAlignment: isUserMessage ? MainAxisAlignment.end : MainAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 4.0, 0.0),
              child: Icon(
                Icons.content_copy,
                color: Theme.of(context).textTheme.bodySmall!.color,
                size: 10.0,
              ),
            ),
            Text(
              'Copy message',
              style: Theme.of(context).textTheme.bodySmall,
            ),
            const SizedBox(
              width: 8,
            ),
          ],
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
    return GestureDetector(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 10),
        width: double.maxFinite,
        decoration: BoxDecoration(
          color: const Color(0xFF1F1F25),
          borderRadius: BorderRadius.circular(12.0),
        ),
        child: Text(optionText, style: Theme.of(context).textTheme.bodyMedium),
      ),
      onTap: () {
        sendMessage(optionText);
      },
    );
  }
}
