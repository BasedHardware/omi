import 'dart:convert';

import 'package:auto_size_text/auto_size_text.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/pages/chat/widgets/files_handler_widget.dart';
import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/chat/widgets/typing_indicator.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'package:shimmer/shimmer.dart';
import 'package:share_plus/share_plus.dart';

import 'markdown_message_widget.dart';

class AIMessage extends StatefulWidget {
  final bool showTypingIndicator;
  final ServerMessage message;
  final Function(String) sendMessage;
  final bool displayOptions;
  final App? appSender;
  final Function(ServerConversation) updateConversation;
  final Function(int) setMessageNps;

  const AIMessage({
    super.key,
    required this.message,
    required this.sendMessage,
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
        buildMessageWidget(
          widget.message,
          widget.sendMessage,
          widget.showTypingIndicator,
          widget.displayOptions,
          widget.appSender,
          widget.updateConversation,
          widget.setMessageNps,
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
  Function(int) sendMessageNps,
) {
  if (message.memories.isNotEmpty) {
    return MemoriesMessageWidget(
        showTypingIndicator: showTypingIndicator,
        messageMemories: message.memories.length > 3 ? message.memories.sublist(0, 3) : message.memories,
        messageText: message.isEmpty ? '...' : message.text.decodeString,
        updateConversation: updateConversation,
        message: message,
        setMessageNps: sendMessageNps,
        date: message.createdAt);
  } else if (message.type == MessageType.daySummary) {
    return DaySummaryWidget(
        showTypingIndicator: showTypingIndicator, messageText: message.text.decodeString, date: message.createdAt);
  } else if (displayOptions) {
    return InitialMessageWidget(
      showTypingIndicator: showTypingIndicator,
      messageText: message.text.decodeString,
      sendMessage: sendMessage,
    );
  } else {
    return NormalMessageWidget(
      showTypingIndicator: showTypingIndicator,
      thinkings: message.thinkings,
      messageText: message.text.decodeString,
      message: message,
      setMessageNps: sendMessageNps,
      createdAt: message.createdAt,
    );
  }
}

class InitialMessageWidget extends StatelessWidget {
  final bool showTypingIndicator;
  final String messageText;
  final Function(String) sendMessage;

  const InitialMessageWidget(
      {super.key, required this.showTypingIndicator, required this.messageText, required this.sendMessage});

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
            : getMarkdownWidget(context, messageText),
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

class NormalMessageWidget extends StatelessWidget {
  final bool showTypingIndicator;
  final String messageText;
  final List<String> thinkings;
  final ServerMessage message;
  final Function(int) setMessageNps;
  final DateTime createdAt;

  const NormalMessageWidget({
    super.key,
    required this.showTypingIndicator,
    required this.messageText,
    required this.message,
    required this.setMessageNps,
    required this.createdAt,
    this.thinkings = const [],
  });

  @override
  Widget build(BuildContext context) {
    var previousThinkingText = message.thinkings.length > 1
        ? message.thinkings
            .sublist(message.thinkings.length - 2 >= 0 ? message.thinkings.length - 2 : 0)
            .first
            .decodeString
        : null;
    var thinkingText = message.thinkings.isNotEmpty ? message.thinkings.last.decodeString : null;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisAlignment: MainAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        FilesHandlerWidget(message: message),
        showTypingIndicator && messageText.isEmpty
            ? Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                decoration: BoxDecoration(
                  color: const Color(0xFF1f1f25),
                  borderRadius: const BorderRadius.only(
                    topLeft: Radius.circular(4.0),
                    topRight: Radius.circular(16.0),
                    bottomRight: Radius.circular(16.0),
                    bottomLeft: Radius.circular(16.0),
                  ),
                ),
                margin: EdgeInsets.only(top: previousThinkingText != null ? 0 : 8),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    thinkingText != null
                        ? Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisAlignment: MainAxisAlignment.start,
                              children: [
                                previousThinkingText != null
                                    ? Text(
                                        overflow: TextOverflow.fade,
                                        maxLines: 1,
                                        softWrap: false,
                                        previousThinkingText,
                                        style: const TextStyle(color: Colors.white60, fontSize: 15),
                                      )
                                    : const SizedBox.shrink(),
                                Shimmer.fromColors(
                                  baseColor: Colors.white,
                                  highlightColor: Colors.grey,
                                  child: Text(
                                    overflow: TextOverflow.fade,
                                    maxLines: 1,
                                    softWrap: false,
                                    thinkingText,
                                    style: const TextStyle(color: Colors.white, fontSize: 15),
                                  ),
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
        messageText.isEmpty
            ? const SizedBox.shrink()
            : Container(
                padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                decoration: BoxDecoration(
                  color: const Color(0xFF1f1f25),
                  borderRadius: const BorderRadius.only(
                    topLeft: Radius.circular(4.0),
                    topRight: Radius.circular(16.0),
                    bottomRight: Radius.circular(16.0),
                    bottomLeft: Radius.circular(16.0),
                  ),
                ),
                child: getMarkdownWidget(context, messageText),
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

  const MemoriesMessageWidget({
    super.key,
    required this.showTypingIndicator,
    required this.messageMemories,
    required this.messageText,
    required this.updateConversation,
    required this.message,
    required this.setMessageNps,
    required this.date,
  });

  @override
  State<MemoriesMessageWidget> createState() => _MemoriesMessageWidgetState();
}

class _MemoriesMessageWidgetState extends State<MemoriesMessageWidget> {
  late List<bool> conversationDetailLoading;

  @override
  void initState() {
    conversationDetailLoading = List.filled(widget.messageMemories.length, false);
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
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
        widget.showTypingIndicator
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
            : getMarkdownWidget(context, widget.messageText),
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
                    context.read<ConversationDetailProvider>().updateConversation(idx, date);
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
                    context.read<ConversationDetailProvider>().updateConversation(idx, date);
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
