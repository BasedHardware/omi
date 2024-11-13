import 'dart:convert';

import 'package:auto_size_text/auto_size_text.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_markdown/flutter_markdown.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/pages/chat/widgets/typing_indicator.dart';
import 'package:friend_private/pages/memory_detail/memory_detail_provider.dart';
import 'package:friend_private/pages/memory_detail/page.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/memory_provider.dart';
import 'package:friend_private/utils/alerts/app_snackbar.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:provider/provider.dart';

class AIMessage extends StatefulWidget {
  final bool showTypingIndicator;
  final ServerMessage message;
  final Function(String) sendMessage;
  final bool displayOptions;
  final App? appSender;
  final Function(ServerMemory) updateMemory;
  final Function(int) setMessageNps;

  const AIMessage({
    super.key,
    required this.message,
    required this.sendMessage,
    required this.displayOptions,
    required this.updateMemory,
    required this.setMessageNps,
    this.appSender,
    this.showTypingIndicator = false,
  });

  @override
  State<AIMessage> createState() => _AIMessageState();
}

class _AIMessageState extends State<AIMessage> {
  late List<bool> memoryDetailLoading;

  @override
  void initState() {
    memoryDetailLoading = List.filled(widget.message.memories.length, false);
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.max,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        widget.appSender != null
            ? CachedNetworkImage(
                imageUrl: widget.appSender!.getImageUrl(),
                imageBuilder: (context, imageProvider) => CircleAvatar(
                  backgroundColor: Colors.white,
                  radius: 16,
                  backgroundImage: imageProvider,
                ),
                placeholder: (context, url) => const CircularProgressIndicator(),
                errorWidget: (context, url, error) => const Icon(Icons.error),
              )
            : Container(
                decoration: const BoxDecoration(
                  image: DecorationImage(
                    image: AssetImage("assets/images/background.png"),
                    fit: BoxFit.cover,
                  ),
                  borderRadius: BorderRadius.all(Radius.circular(16.0)),
                ),
                height: 32,
                width: 32,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    Image.asset(
                      "assets/images/herologo.png",
                      height: 24,
                      width: 24,
                    ),
                  ],
                ),
              ),
        const SizedBox(width: 16.0),
        Expanded(
          child: Column(
            mainAxisSize: MainAxisSize.max,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const SizedBox(height: 6),
              buildMessageWidget(
                widget.message,
                widget.sendMessage,
                widget.showTypingIndicator,
                widget.displayOptions,
                widget.appSender,
                widget.updateMemory,
                widget.setMessageNps,
              ),
            ],
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
  Function(ServerMemory) updateMemory,
  Function(int) sendMessageNps,
) {
  if (message.memories.isNotEmpty) {
    return MemoriesMessageWidget(
      showTypingIndicator: showTypingIndicator,
      messageMemories: message.memories.length > 3 ? message.memories.sublist(0, 3) : message.memories,
      messageText: message.isEmpty ? '...' : message.text.decodeString,
      updateMemory: updateMemory,
      message: message,
      setMessageNps: sendMessageNps,
    );
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
      messageText: message.text.decodeString,
      message: message,
      setMessageNps: sendMessageNps,
    );
  }
}

Widget _getMarkdownWidget(BuildContext context, String content) {
  var style = TextStyle(color: Colors.grey.shade300, fontSize: 15, height: 1.3);
  return MarkdownBody(
    shrinkWrap: true,
    styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
      a: style,
      p: style,
      blockquote: style.copyWith(
        backgroundColor: Colors.transparent,
        color: Colors.black,
      ),
      blockquoteDecoration: BoxDecoration(
        color: Colors.grey.shade800,
        borderRadius: BorderRadius.circular(4),
      ),
      code: style.copyWith(
        backgroundColor: Colors.transparent,
        decoration: TextDecoration.none,
        color: Colors.white,
        fontWeight: FontWeight.w600,
      ),
    ),
    data: content,
  );
}

Widget _getNpsWidget(BuildContext context, ServerMessage message, Function(int) setMessageNps) {
  if (!message.askForNps) return const SizedBox();

  return Padding(
    padding: const EdgeInsetsDirectional.only(top: 8),
    child: Row(
      mainAxisAlignment: MainAxisAlignment.start,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Text('Was this helpful?', style: TextStyle(fontWeight: FontWeight.w600, color: Colors.grey.shade300)),
        IconButton(
          onPressed: () {
            setMessageNps(0);
            AppSnackbar.showSnackbar('Thank you for your feedback!');
          },
          icon: const Icon(Icons.thumb_down_alt_outlined, size: 20, color: Colors.red),
        ),
        IconButton(
          onPressed: () {
            setMessageNps(1);
            AppSnackbar.showSnackbar('Thank you for your feedback!');
          },
          icon: const Icon(Icons.thumb_up_alt_outlined, size: 20, color: Colors.green),
        ),
      ],
    ),
  );
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
        SelectionArea(
            child: showTypingIndicator
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
                : _getMarkdownWidget(context, messageText)
            // AutoSizeText(
            //         messageText,
            // style: TextStyle(fontSize: 15.0, fontWeight: FontWeight.w500, color: Colors.grey.shade300),
            // ),
            ),
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
        SelectionArea(
          child: showTypingIndicator
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
        ),
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
              fontSize: 14,
              fontWeight: FontWeight.bold,
              color: Colors.grey.shade500,
            ),
          ),
          title: AutoSizeText(
            sentences[index],
            style: const TextStyle(
              fontSize: 15.0,
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
  final ServerMessage message;
  final Function(int) setMessageNps;

  const NormalMessageWidget({
    super.key,
    required this.showTypingIndicator,
    required this.messageText,
    required this.message,
    required this.setMessageNps,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SelectionArea(
          child: showTypingIndicator
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
              : _getMarkdownWidget(context, messageText),
          // AutoSizeText(
          //         messageText,
          //         // : utf8.decode(widget.message.text.codeUnits),
          //         style: TextStyle(fontSize: 15.0, fontWeight: FontWeight.w500, color: Colors.grey.shade300),
          //       ),
        ),
        _getNpsWidget(context, message, setMessageNps),
        CopyButton(messageText: messageText),
      ],
    );
  }
}

class MemoriesMessageWidget extends StatefulWidget {
  final bool showTypingIndicator;
  final List<MessageMemory> messageMemories;
  final String messageText;
  final Function(ServerMemory) updateMemory;
  final ServerMessage message;
  final Function(int) setMessageNps;

  const MemoriesMessageWidget({
    super.key,
    required this.showTypingIndicator,
    required this.messageMemories,
    required this.messageText,
    required this.updateMemory,
    required this.message,
    required this.setMessageNps,
  });

  @override
  State<MemoriesMessageWidget> createState() => _MemoriesMessageWidgetState();
}

class _MemoriesMessageWidgetState extends State<MemoriesMessageWidget> {
  late List<bool> memoryDetailLoading;

  @override
  void initState() {
    memoryDetailLoading = List.filled(widget.messageMemories.length, false);
    super.initState();
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        SelectionArea(
            child: widget.showTypingIndicator
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
                : _getMarkdownWidget(context, widget.messageText)
            // AutoSizeText(
            //         widget.messageText,
            //         style: TextStyle(fontSize: 15.0, fontWeight: FontWeight.w500, color: Colors.grey.shade300),
            //       ),
            ),
        CopyButton(messageText: widget.messageText),
        const SizedBox(height: 16),
        for (var data in widget.messageMemories.indexed) ...[
          Padding(
            padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 4.0),
            child: GestureDetector(
              onTap: () async {
                final connectivityProvider = Provider.of<ConnectivityProvider>(context, listen: false);
                if (connectivityProvider.isConnected) {
                  var memProvider = Provider.of<MemoryProvider>(context, listen: false);
                  var idx = -1;
                  var date = DateTime(data.$2.createdAt.year, data.$2.createdAt.month, data.$2.createdAt.day);
                  idx = memProvider.groupedMemories[date]?.indexWhere((element) => element.id == data.$2.id) ?? -1;

                  if (idx != -1) {
                    context.read<MemoryDetailProvider>().updateMemory(idx, date);
                    var m = memProvider.groupedMemories[date]![idx];
                    MixpanelManager().chatMessageMemoryClicked(m);
                    await Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (c) => MemoryDetailPage(
                          memory: m,
                        ),
                      ),
                    );
                  } else {
                    if (memoryDetailLoading[data.$1]) return;
                    setState(() => memoryDetailLoading[data.$1] = true);
                    ServerMemory? m = await getMemoryById(data.$2.id);
                    if (m == null) return;
                    (idx, date) = memProvider.addMemoryWithDateGrouped(m);
                    MixpanelManager().chatMessageMemoryClicked(m);
                    setState(() => memoryDetailLoading[data.$1] = false);
                    context.read<MemoryDetailProvider>().updateMemory(idx, date);
                    await Navigator.of(context).push(
                      MaterialPageRoute(
                        builder: (c) => MemoryDetailPage(
                          memory: m,
                        ),
                      ),
                    );
                    if (SharedPreferencesUtil().modifiedMemoryDetails?.id == m.id) {
                      ServerMemory modifiedDetails = SharedPreferencesUtil().modifiedMemoryDetails!;
                      widget.updateMemory(SharedPreferencesUtil().modifiedMemoryDetails!);
                      var copy = List<MessageMemory>.from(widget.messageMemories);
                      copy[data.$1] = MessageMemory(
                          modifiedDetails.id,
                          modifiedDetails.createdAt,
                          MessageMemoryStructured(
                            modifiedDetails.structured.title,
                            modifiedDetails.structured.emoji,
                          ));
                      widget.messageMemories.clear();
                      widget.messageMemories.addAll(copy);
                      SharedPreferencesUtil().modifiedMemoryDetails = null;
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
                  color: Colors.grey.shade900,
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
                    memoryDetailLoading[data.$1]
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
        _getNpsWidget(context, widget.message, widget.setMessageNps),
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

  const CopyButton({super.key, required this.messageText});

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(0.0, 6.0, 0.0, 0.0),
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
                'Response copied to clipboard.',
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
              'Copy response',
              style: Theme.of(context).textTheme.bodySmall,
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
          color: Colors.grey.shade900,
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
