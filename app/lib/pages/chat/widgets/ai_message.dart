import 'dart:convert';

import 'package:auto_size_text/auto_size_text.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/http/api/memories.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/pages/memory_detail/page.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/connectivity_controller.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:friend_private/widgets/extensions/string.dart';

class AIMessage extends StatefulWidget {
  final ServerMessage message;
  final Function(String) sendMessage;
  final bool displayOptions;
  final Plugin? pluginSender;
  final Function(ServerMemory) updateMemory;

  const AIMessage({
    super.key,
    required this.message,
    required this.sendMessage,
    required this.displayOptions,
    this.pluginSender,
    required this.updateMemory,
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
    var messageMemories =
        widget.message.memories.length > 3 ? widget.message.memories.sublist(0, 3) : widget.message.memories;
    final message = widget.message.text;
    final messageText = message.isEmpty
        ? '...'
        // : message.text.replaceAll(r'\n', '\n').replaceAll('**', '').replaceAll('\\"', '\"'),
        : message.decodeSting;
    return Row(
      mainAxisSize: MainAxisSize.max,
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        widget.pluginSender != null
            ? CachedNetworkImage(
                imageUrl: widget.pluginSender!.getImageUrl(),
                imageBuilder: (context, imageProvider) => Container(
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    image: DecorationImage(
                      image: imageProvider,
                      fit: BoxFit.cover,
                    ),
                  ),
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
              widget.message.type == MessageType.daySummary
                  ? Text(
                      '📅  Day Summary ~ ${dateTimeFormat('MMM, dd', DateTime.now())}',
                      style: TextStyle(
                        fontSize: 18,
                        fontWeight: FontWeight.w500,
                        color: Colors.grey.shade300,
                        decoration: TextDecoration.underline,
                      ),
                    )
                  : const SizedBox(),
              widget.message.type == MessageType.daySummary ? const SizedBox(height: 16) : const SizedBox(),
              SelectionArea(
                  child: AutoSizeText(
                messageText,
                // : utf8.decode(widget.message.text.codeUnits),
                style: TextStyle(fontSize: 15.0, fontWeight: FontWeight.w500, color: Colors.grey.shade300),
              )),
              if (widget.message.id != 1) _getCopyButton(context), // RESTORE ME
              // if (message.id == 1 && displayOptions) const SizedBox(height: 8),
              // if (message.id == 1 && displayOptions) ..._getInitialOptions(context),
              if (messageMemories.isNotEmpty) ...[
                const SizedBox(height: 16),
                for (var data in messageMemories.indexed) ...[
                  Padding(
                    padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 4.0),
                    child: GestureDetector(
                      onTap: () async {
                        if (ConnectivityController().isConnected.value) {
                          if (memoryDetailLoading[data.$1]) return;
                          setState(() => memoryDetailLoading[data.$1] = true);

                          ServerMemory? m = await getMemoryById(data.$2.id);
                          if (m == null) return;
                          MixpanelManager().chatMessageMemoryClicked(m);
                          setState(() => memoryDetailLoading[data.$1] = false);
                          await Navigator.of(context)
                              .push(MaterialPageRoute(builder: (c) => MemoryDetailPage(memory: m)));
                          if (SharedPreferencesUtil().modifiedMemoryDetails?.id == m.id) {
                            ServerMemory modifiedDetails = SharedPreferencesUtil().modifiedMemoryDetails!;
                            widget.updateMemory(SharedPreferencesUtil().modifiedMemoryDetails!);
                            var copy = List<MessageMemory>.from(widget.message.memories);
                            copy[data.$1] = MessageMemory(
                                modifiedDetails.id,
                                modifiedDetails.createdAt,
                                MessageMemoryStructured(
                                  modifiedDetails.structured.title,
                                  modifiedDetails.structured.emoji,
                                ));
                            widget.message.memories.clear();
                            widget.message.memories.addAll(copy);
                            SharedPreferencesUtil().modifiedMemoryDetails = null;
                            setState(() {});
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
                                '${utf8.decode(data.$2.structured.emoji.codeUnits)} ${data.$2.structured.title}',
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
              ],
            ],
          ),
        ),
      ],
    );
  }

  _getCopyButton(BuildContext context) {
    return Padding(
      padding: const EdgeInsetsDirectional.fromSTEB(0.0, 6.0, 0.0, 0.0),
      child: InkWell(
        splashColor: Colors.transparent,
        focusColor: Colors.transparent,
        hoverColor: Colors.transparent,
        highlightColor: Colors.transparent,
        onTap: () async {
          await Clipboard.setData(ClipboardData(text: widget.message.text));
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

  _getInitialOption(BuildContext context, String optionText) {
    return GestureDetector(
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12.0, vertical: 8),
        width: double.maxFinite,
        decoration: BoxDecoration(
          color: Colors.grey.shade900,
          borderRadius: BorderRadius.circular(12.0),
        ),
        child: Text(optionText, style: Theme.of(context).textTheme.bodyMedium),
      ),
      onTap: () {
        widget.sendMessage(optionText);
      },
    );
  }

  _getInitialOptions(BuildContext context) {
    return [
      const SizedBox(height: 8),
      _getInitialOption(context, 'What tasks do I have from yesterday?'),
      const SizedBox(height: 8),
      _getInitialOption(context, 'What conversations did I have with John?'),
      const SizedBox(height: 8),
      _getInitialOption(context, 'What advise have I received about entrepreneurship?'),
    ];
  }
}
