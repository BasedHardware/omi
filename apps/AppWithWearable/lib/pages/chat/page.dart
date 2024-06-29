import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/api_requests/api/pinecone.dart';
import 'package:friend_private/backend/api_requests/api/prompt.dart';
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
import 'package:instabug_flutter/instabug_flutter.dart';
import 'package:tuple/tuple.dart';

class ChatPage extends StatefulWidget {
  final FocusNode textFieldFocusNode;
  final List<Message> messages;
  final VoidCallback refreshMessages;

  const ChatPage({
    super.key,
    required this.textFieldFocusNode,
    required this.messages,
    required this.refreshMessages,
  });

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> with AutomaticKeepAliveClientMixin {
  TextEditingController textController = TextEditingController();
  ScrollController scrollController = ScrollController();

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
      var memories = MemoryProvider().retrieveDayMemories(now);
      if (memories.isEmpty) {
        SharedPreferencesUtil().lastDailySummaryDay = DateTime.now().toIso8601String();
        return;
      }

      var message = Message(DateTime.now(), '', 'ai', type: 'daySummary');
      MessageProvider().saveMessage(message);
      setState(() => widget.messages.add(message));

      var result = await dailySummaryNotifications(memories);
      SharedPreferencesUtil().lastDailySummaryDay = DateTime.now().toIso8601String();
      message.text = result;
      message.memories.addAll(memories);
      MessageProvider().updateMessage(message);
      setState(() => widget.messages.last = message);
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
    scrollController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Stack(
      children: [
        SingleChildScrollView(
          controller: scrollController,
          child: ListView.builder(
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: widget.messages.length,
            itemBuilder: (context, chatIndex) {
              final message = widget.messages[chatIndex];
              final isLastMessage = chatIndex == widget.messages.length - 1;
              double topPadding = chatIndex == 0 ? 24 : 8;
              double bottomPadding = isLastMessage ? (widget.textFieldFocusNode.hasFocus ? 120 : 200) : 0;
              return Padding(
                key: ValueKey(message.id),
                padding: EdgeInsets.only(bottom: bottomPadding, left: 18, right: 18, top: topPadding),
                child: message.senderEnum == MessageSender.ai
                    ? AIMessage(
                        message: message,
                        sendMessage: _sendMessageUtil,
                        displayOptions: widget.messages.length <= 1,
                        memories: message.memories,
                      )
                    : HumanMessage(message: message),
              );
            },
          ),
        ),
        Align(
          alignment: Alignment.bottomCenter,
          child: Container(
            width: double.maxFinite,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 2),
            margin: EdgeInsets.only(left: 18, right: 18, bottom: widget.textFieldFocusNode.hasFocus ? 40 : 120),
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
              textAlign: TextAlign.start,
              textAlignVertical: TextAlignVertical.center,
              decoration: InputDecoration(
                hintText: 'Ask your Friend anything',
                hintStyle: const TextStyle(fontSize: 14.0, color: Colors.grey),
                focusedBorder: InputBorder.none,
                enabledBorder: InputBorder.none,
                suffixIcon: IconButton(
                  splashColor: Colors.transparent,
                  splashRadius: 1,
                  onPressed: loading
                      ? null
                      : () async {
                          String message = textController.text;
                          if (message.isEmpty) return;
                          _sendMessageUtil(message);
                        },
                  icon: loading
                      ? const SizedBox(
                          width: 16,
                          height: 16,
                          child: CircularProgressIndicator(
                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                          ),
                        )
                      : const Icon(
                          Icons.send_rounded,
                          color: Color(0xFFF7F4F4),
                          size: 24.0,
                        ),
                ),
              ),
              // maxLines: 8,
              // minLines: 1,
              // keyboardType: TextInputType.multiline,
              style: TextStyle(fontSize: 14.0, color: Colors.grey.shade200),
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
    await streamApiResponse(ragContext, _callbackFunctionChatStreaming(aiMessage), () {
      aiMessage.memories.addAll(memories);
      MessageProvider().updateMessage(aiMessage);
      widget.refreshMessages();
      if (memories.isNotEmpty) _moveListToBottom(extra: (70 * memories.length).toDouble());
    });
    changeLoadingState();
  }

  Future<List<dynamic>> _retrieveRAGContext(String message) async {
    Tuple2<List<String>, List<DateTime>>? context =
        await determineRequiresContext(await MessageProvider().retrieveMostRecentMessages(limit: 10));
    debugPrint('_retrieveRAGContext betterContextQuestion: $context');
    if (context == null || (context.item1.isEmpty && context.item2.isEmpty)) {
      return ['', []];
    }
    List<String> topics = context.item1;
    List<DateTime> datesRange = context.item2;
    var startTimestamp = datesRange.isNotEmpty ? datesRange[0].millisecondsSinceEpoch ~/ 1000 : null;
    var endTimestamp = datesRange.isNotEmpty ? datesRange[1].millisecondsSinceEpoch ~/ 1000 : null;

    // throw Exception('testing');
    // TODO: I feel like this always return the same memories? Test more.
    // TODO: how to show all the memories used in the chat, maybe a expand toggle?
    Future<List<List<String>>> memoriesByTopic = Future.wait(topics.map((topic) async {
      try {
        List<double> vectorizedMessage = await getEmbeddingsFromInput(topic);
        List<String> memoriesId =
            await queryPineconeVectors(vectorizedMessage, startTimestamp: startTimestamp, endTimestamp: endTimestamp);
        debugPrint('queryPineconeVectors memories retrieved for topic $topic: ${memoriesId.length}');
        return memoriesId;
      } catch (e, stacktrace) {
        CrashReporting.reportHandledCrash(e, stacktrace, level: NonFatalExceptionLevel.error, userAttributes: {
          'message_length': message.length.toString(),
          'topics_count': topics.length.toString(),
          // 'topic_failed': topic,
          // TODO: would it be okay to the vectorizedMessage instead? so we can replicate without knowing the message
        });
        return [];
      }
    }));
    List<Memory> memories = [];
    if (topics.isNotEmpty) {
      List<List<String>> memoriesIdList = await memoriesByTopic;
      List<String> memoriesId = memoriesIdList.reduce((value, element) => value + element).toSet().toList();
      debugPrint('queryPineconeVectors memories from topics: ${memoriesId.length}');
      List<int> memoriesIdAsInt = memoriesId.map((e) => int.tryParse(e) ?? -1).where((e) => e != -1).toList();
      memories = MemoryProvider().getMemoriesById(memoriesIdAsInt);
    }

    if (topics.isEmpty && datesRange.isNotEmpty) {
      memories = MemoryProvider().retrieveMemoriesWithinDates(datesRange[0], datesRange[1]);
      debugPrint('queryPineconeVectors memories from dates: ${memories.length}');
    }
    return [Memory.memoriesToString(memories), memories];
  }

  _prepareStreaming(String text) {
    textController.clear(); // setState if isolated
    var human = Message(DateTime.now(), text, 'human');
    var ai = Message(DateTime.now(), '', 'ai');
    MessageProvider().saveMessage(human);
    MessageProvider().saveMessage(ai);
    widget.messages.add(human);
    widget.messages.add(ai);
    _moveListToBottom(extra: widget.textFieldFocusNode.hasFocus ? 148 : 200);
    return ai;
  }

  _callbackFunctionChatStreaming(Message aiMessage) {
    return (String content) async {
      aiMessage.text = '${aiMessage.text}$content';
      MessageProvider().updateMessage(aiMessage);
      widget.messages.removeLast();
      widget.messages.add(aiMessage);
      setState(() {});
      _moveListToBottom();
    };
  }

  _moveListToBottom({double extra = 0}) async {
    try {
      scrollController.jumpTo(scrollController.position.maxScrollExtent + extra);
    } catch (e) {
      debugPrint(e.toString());
    }
  }
}
