import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/api_requests/stream_api_response.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/message.dart';
import 'package:friend_private/pages/chat/widgets/ai_message.dart';
import 'package:friend_private/pages/chat/widgets/user_message.dart';
import 'package:friend_private/utils/temp.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:uuid/uuid.dart';

class ChatPage extends StatefulWidget {
  final FocusNode textFieldFocusNode;
  final List<Memory> memories;
  final Function(List<Message>) setMessages;
  final Function(Message, bool) addMessage;
  final List<Message> messages;

  const ChatPage({
    super.key,
    required this.textFieldFocusNode,
    required this.memories,
    required this.messages,
    required this.setMessages,
    required this.addMessage,
  });

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> with AutomaticKeepAliveClientMixin {
  TextEditingController textController = TextEditingController();
  ScrollController listViewController = ScrollController();

  var prefs = SharedPreferencesUtil();

  final scaffoldKey = GlobalKey<ScaffoldState>();
  bool loading = false;

  changeLoadingState() {
    setState(() {
      loading = !loading;
    });
  }

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    super.initState();
    SchedulerBinding.instance.addPostFrameCallback((_) {
      _moveListToBottom();
    });
  }

  @override
  void dispose() {
    textController.dispose();
    listViewController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Stack(
      children: [
        Align(
          alignment: Alignment.bottomCenter,
          child: ListView.builder(
            scrollDirection: Axis.vertical,
            controller: listViewController,
            itemCount: widget.messages.length,
            itemBuilder: (context, chatIndex) {
              final message = widget.messages[chatIndex];
              final isLastMessage = chatIndex == widget.messages.length - 1;
              double topPadding = chatIndex == 0 ? 24 : 0;
              double bottomPadding = isLastMessage ? (widget.textFieldFocusNode.hasFocus ? 120 : 180) : 0;
              return Padding(
                key: ValueKey(message.id),
                padding: EdgeInsets.only(bottom: bottomPadding, left: 18, right: 18, top: topPadding),
                child: message.type == 'ai'
                    ? AIMessage(
                        message: message,
                        sendMessage: _sendMessageUtil,
                        displayOptions: widget.messages.length <= 1,
                        memories: widget.memories
                            .where((m) => message.memoryIds?.contains(m.id.toString()) ?? false)
                            .toList(),
                      )
                    : HumanMessage(message: message),
              );
            },
          ),
        ),
        Align(
          alignment: Alignment.bottomCenter,
          child: Padding(
            padding: EdgeInsets.only(bottom: widget.textFieldFocusNode.hasFocus ? 40 : 120),
            child: Container(
              width: double.maxFinite,
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
              margin: const EdgeInsets.fromLTRB(18, 0, 18, 0),
              decoration: const BoxDecoration(
                color: Colors.black,
                borderRadius: BorderRadius.all(Radius.circular(16)),
                border: GradientBoxBorder(
                  gradient: LinearGradient(colors: [
                    Color.fromARGB(127, 208, 208, 208),
                    Color.fromARGB(127, 188, 99, 121),
                    Color.fromARGB(127, 86, 101, 182),
                    Color.fromARGB(127, 126, 190, 236)
                  ]),
                  width: 1,
                ),
                shape: BoxShape.rectangle,
              ),
              child: TextField(
                enabled: true,
                controller: textController,
                // textCapitalization: TextCapitalization.sentences,
                obscureText: false,
                focusNode: widget.textFieldFocusNode,
                // canRequestFocus: true,
                decoration: InputDecoration(
                    hintText: 'Ask your Friend anything',
                    hintStyle: const TextStyle(fontSize: 14.0, color: Colors.grey),
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                    suffixIcon: IconButton(
                      icon: loading
                          ? const SizedBox(
                              width: 24,
                              height: 24,
                              child: CircularProgressIndicator(
                                valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                              ),
                            )
                          : const Icon(
                              Icons.send_rounded,
                              color: Color(0xFFF7F4F4),
                              size: 30.0,
                            ),
                      onPressed: loading
                          ? null
                          : () async {
                              String message = textController.text;
                              if (message.isEmpty) return;
                              _sendMessageUtil(message);
                            },
                    )),
                // maxLines: 8,
                // minLines: 1,
                // keyboardType: TextInputType.multiline,
                style: TextStyle(fontSize: 14.0, color: Colors.grey.shade200),
              ),
            ),
          ),
        ),
      ],
    );
  }

  _sendMessageUtil(String message) async {
    changeLoadingState();
    _prepareStreaming(message);
    dynamic ragInfo = await _retrieveRAGContext(message);
    String ragContext = ragInfo[0];
    List<String> memoryIds = ragInfo[1].cast<String>();
    debugPrint('RAG Context: $ragContext');
    MixpanelManager().chatMessageSent(message);

    final pluginsEnabled = SharedPreferencesUtil().pluginsEnabled;
    final pluginsList = SharedPreferencesUtil().pluginsList;
    final enabledPlugins = pluginsList.where((e) => pluginsEnabled.contains(e.id)).toList();

    // set personality to empty string if no plugins enabled
    dynamic personality = enabledPlugins.isNotEmpty 
        ? (enabledPlugins.length > 1 
            ? enabledPlugins.map((e) => e.prompt).toList() 
            : enabledPlugins.first.prompt) 
        : "";

    await streamApiResponse(personality, ragContext, _callbackFunctionChatStreaming(memoryIds), _messages, () {
      _messages.last.memoryIds = memoryIds;
      prefs.chatMessages = _messages;
    // TODO: make sure about few things here
    //     await streamApiResponse(ragContext, _callbackFunctionChatStreaming(memoryIds), widget.messages, () {
    //       widget.messages.last.memoryIds = memoryIds;
    //       prefs.chatMessages = widget.messages;
    });
    changeLoadingState();
  }

  Future<List<dynamic>> _retrieveRAGContext(String message) async {
    String? betterContextQuestion = await determineRequiresContext(retrieveMostRecentMessages(widget.messages));
    debugPrint('_retrieveRAGContext betterContextQuestion: $betterContextQuestion');
    if (betterContextQuestion == null || betterContextQuestion.isEmpty) {
      return ['', []];
    }
    List<double> vectorizedMessage = await getEmbeddingsFromInput(betterContextQuestion);
    List<String> memoriesId = await queryPineconeVectors(vectorizedMessage);
    debugPrint('queryPineconeVectors memories retrieved: $memoriesId');
    if (memoriesId.isEmpty) {
      return ['', []];
    }
    List<int> memoriesIdAsInt = memoriesId.map((e) => int.tryParse(e) ?? -1).where((e) => e != -1).toList();
    debugPrint('memoriesIdAsInt: $memoriesIdAsInt');
    List<Memory> memories = await MemoryProvider().getMemoriesById(memoriesIdAsInt);
    return [Memory.memoriesToString(memories), memoriesId];
  }

  _prepareStreaming(String text) {
    textController.clear(); // setState if isolated
    widget.addMessage(Message(text: text, type: 'human', id: const Uuid().v4()), true);
    widget.addMessage(Message(text: '', type: 'ai', id: const Uuid().v4()), false);
    _moveListToBottom(extra: 0);
  }

  _callbackFunctionChatStreaming(List<String> memoryIds) {
    return (String content) async {
      debugPrint('Content: $content');
      var messagesCopy = [...widget.messages];
      messagesCopy.last.text += content;
      // TODO: better way for this?
      debugPrint(messagesCopy.last.text);
      widget.setMessages(messagesCopy);
      setState(() {});
      _moveListToBottom();
    };
  }

  _moveListToBottom({double extra = 0}) async {
    listViewController.jumpTo(listViewController.position.maxScrollExtent + extra);
  }
}
