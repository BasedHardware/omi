import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/api_requests/stream_api_response.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/backend/storage/message.dart';
import 'package:friend_private/pages/chat/widgets/ai_message.dart';
import 'package:friend_private/pages/chat/widgets/user_message.dart';
import 'package:friend_private/utils/temp.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:uuid/uuid.dart';

class ChatPage extends StatefulWidget {
  final FocusNode textFieldFocusNode;
  final List<Memory> memories;

  const ChatPage({
    super.key,
    required this.textFieldFocusNode,
    required this.memories,
  });

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> with AutomaticKeepAliveClientMixin {
  TextEditingController textController = TextEditingController();
  ScrollController listViewController = ScrollController();

  List<Message> _messages = [];
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
    var msg = prefs.chatMessages;
    _messages =
        msg.isEmpty ? [Message(text: 'What would you like to search for?', type: 'ai', id: '1')] : prefs.chatMessages;
    SchedulerBinding.instance.addPostFrameCallback((_) {
      _moveListToBottom(initial: true);
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
        Container(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
          child: Column(
            children: [
              Expanded(
                  child: ListView.builder(
                scrollDirection: Axis.vertical,
                controller: listViewController,
                itemCount: _messages.length,
                itemBuilder: (context, chatIndex) {
                  final message = _messages[chatIndex];
                  if (message.type == 'ai') {
                    var messageMemoriesId = Set<String>.from(message.memoryIds ?? []);
                    return Padding(
                      padding: EdgeInsets.only(
                          bottom: chatIndex == _messages.length - 1
                              ? widget.textFieldFocusNode.hasFocus
                                  ? 120
                                  : 160
                              : 0),
                      child: AIMessage(
                        message: message,
                        sendMessage: _sendMessageUtil,
                        displayOptions: _messages.length <= 1,
                        memories: widget.memories.where((m) => messageMemoriesId.contains(m.id.toString())).toList(),
                      ),
                    );
                  }
                  return Padding(
                    padding: EdgeInsets.only(
                        bottom: chatIndex == _messages.length - 1
                            ? widget.textFieldFocusNode.hasFocus
                                ? 120
                                : 160
                            : 0),
                    child: HumanMessage(message: message),
                  );
                },
              )),
              // const SizedBox(height: 160),
            ],
          ),
        ),
        Align(
          alignment: Alignment.bottomCenter,
          child: Padding(
            padding: EdgeInsets.only(bottom: widget.textFieldFocusNode.hasFocus ? 40 : 120),
            child: Container(
              width: double.maxFinite,
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
              margin: const EdgeInsets.fromLTRB(32, 0, 32, 0),
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
    await streamApiResponse(ragContext, _callbackFunctionChatStreaming(memoryIds), _messages, () {
      _messages.last.memoryIds = memoryIds;
      prefs.chatMessages = _messages;
    });
    changeLoadingState();
  }

  Future<List<dynamic>> _retrieveRAGContext(String message) async {
    String? betterContextQuestion = await determineRequiresContext(retrieveMostRecentMessages(_messages));
    debugPrint('_retrieveRAGContext betterContextQuestion: $betterContextQuestion');
    if (betterContextQuestion == null) {
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
    var messagesCopy = [..._messages];
    messagesCopy.add(Message(text: text, type: 'human', id: const Uuid().v4()));
    setState(() {
      // update locally
      _messages = messagesCopy;
      textController.clear();
    });
    prefs.chatMessages = messagesCopy;
    _moveListToBottom();
    // include initial empty message for streaming to save in
    _messages.add(Message(text: '', type: 'ai', id: const Uuid().v4()));
  }

  _callbackFunctionChatStreaming(List<String> memoryIds) {
    return (String content) async {
      debugPrint('Content: $content');
      var messagesCopy = [..._messages];
      messagesCopy.last.text += content;
      debugPrint(messagesCopy.last.text);
      setState(() {
        _messages = messagesCopy;
      });
      _moveListToBottom();
    };
  }

  _moveListToBottom({bool initial = false}) async {
    listViewController.jumpTo(listViewController.position.maxScrollExtent + (initial ? 240 : 0));
  }
}
