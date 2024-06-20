import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/api_requests/stream_api_response.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/database/message.dart';
import 'package:friend_private/backend/database/message_provider.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/pages/chat/widgets/ai_message.dart';
import 'package:friend_private/pages/chat/widgets/user_message.dart';
import 'package:gradient_borders/gradient_borders.dart';

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

  _initDailySummary() {
    Timer.periodic(const Duration(seconds: 1), (timer) async {
      var now = DateTime.now();
      if (now.hour < 20) return;
      // TODO: maybe a better way to optimize this. is it better to do on build state?
      debugPrint('now: $now');
      if (SharedPreferencesUtil().lastDailySummaryDay != '') {
        var secondsFrom8pm = now.difference(DateTime(now.year, now.month, now.day, 20)).inSeconds;
        var at = DateTime.parse(SharedPreferencesUtil().lastDailySummaryDay);
        var secondsFromLast = now.difference(at).inSeconds;
        debugPrint('secondsFrom8pm: $secondsFrom8pm');
        debugPrint('secondsFromLast: $secondsFromLast');
        if (secondsFromLast < secondsFrom8pm) {
          timer.cancel();
          return;
        }
      }
      timer.cancel();
      var message = Message(DateTime.now(), '', 'ai', type: 'daySummary');
      MessageProvider().saveMessage(message);

      var memories = await MemoryProvider().retrieveDayMemories(now);
      var result = await dailySummaryNotifications(memories);
      SharedPreferencesUtil().lastDailySummaryDay = DateTime.now().toIso8601String();
      message.text = result;
      message.memories.addAll(memories);
      MessageProvider().updateMessage(message);
      _moveListToBottom();
    });
  }

  @override
  void initState() {
    SchedulerBinding.instance.addPostFrameCallback((_) {
      _moveListToBottom();
    });
    _initDailySummary();
    super.initState();
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
          child: StreamBuilder(
            stream: MessageProvider().getMessagesStreamed(),
            builder: (context, snapshot) {
              if (snapshot.connectionState == ConnectionState.waiting) {
                return const Center(child: CircularProgressIndicator());
              }
              if (snapshot.hasError) {
                return const Center(child: Text('An error occurred'));
              }
              if (snapshot.data == null) {
                return const Center(child: Text('No messages found'));
              }
              List<Message> messages = snapshot.data!.find();
              return ListView.builder(
                scrollDirection: Axis.vertical,
                controller: listViewController,
                itemCount: messages.length,
                itemBuilder: (context, chatIndex) {
                  final message = messages[chatIndex];
                  final isLastMessage = chatIndex == messages.length - 1;
                  double topPadding = chatIndex == 0 ? 24 : 8;
                  double bottomPadding = isLastMessage ? (widget.textFieldFocusNode.hasFocus ? 120 : 200) : 0;
                  return Padding(
                    key: ValueKey(message.id),
                    padding: EdgeInsets.only(bottom: bottomPadding, left: 18, right: 18, top: topPadding),
                    child: message.senderEnum == MessageSender.ai
                        ? AIMessage(
                            message: message,
                            sendMessage: _sendMessageUtil,
                            displayOptions: messages.length <= 1,
                            memories: message.memories,
                          )
                        : HumanMessage(message: message),
                  );
                },
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
    Message aiMessage = await _prepareStreaming(message);
    dynamic ragInfo = await _retrieveRAGContext(message);
    String ragContext = ragInfo[0];
    List<Memory> memories = ragInfo[1].cast<Memory>();
    debugPrint('RAG Context: $ragContext memories: ${memories.length}');
    MixpanelManager().chatMessageSent(message);
    // TODO: make sure about few things here
    await streamApiResponse(ragContext, _callbackFunctionChatStreaming(aiMessage), () {
      aiMessage.memories.addAll(memories);
    });
    changeLoadingState();
  }

  Future<List<dynamic>> _retrieveRAGContext(String message) async {
    String? betterContextQuestion =
        await determineRequiresContext(await MessageProvider().retrieveMostRecentMessages(limit: 5));
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
    return [Memory.memoriesToString(memories), memories];
  }

  _prepareStreaming(String text) {
    textController.clear(); // setState if isolated
    MessageProvider().saveMessage(Message(DateTime.now(), text, 'human'));
    var aiMessage = Message(DateTime.now(), '', 'ai');
    MessageProvider().saveMessage(aiMessage);
    _moveListToBottom(extra: 0);
    return aiMessage;
  }

  _callbackFunctionChatStreaming(Message aiMessage) {
    return (String content) async {
      debugPrint('Content: $content');
      aiMessage.text = '${aiMessage.text}$content';
      MessageProvider().saveMessage(aiMessage);
      _moveListToBottom();
    };
  }

  _moveListToBottom({double extra = 0}) async {
    listViewController.jumpTo(listViewController.position.maxScrollExtent + extra);
  }
}
