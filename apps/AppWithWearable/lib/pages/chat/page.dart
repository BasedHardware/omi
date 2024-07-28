import 'dart:async';

import 'package:collection/collection.dart';
import 'package:deepgram_speech_to_text/deepgram_speech_to_text.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/api_requests/api/prompt.dart';
import 'package:friend_private/backend/api_requests/stream_api_response.dart';
import 'package:friend_private/backend/database/memory.dart';
import 'package:friend_private/backend/database/memory_provider.dart';
import 'package:friend_private/backend/database/message.dart';
import 'package:friend_private/backend/database/message_provider.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/pages/chat/deepgram_service.dart';
import 'package:friend_private/pages/chat/widgets/ai_message.dart';
import 'package:friend_private/pages/chat/widgets/user_message.dart';
import 'package:friend_private/utils/rag.dart';
import 'package:gradient_borders/gradient_borders.dart';

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
  State<ChatPage> createState() => ChatPageState();
}

class ChatPageState extends State<ChatPage> with AutomaticKeepAliveClientMixin {
  TextEditingController textController = TextEditingController();
  ScrollController scrollController = ScrollController();
  DeepgramService deepgramService = DeepgramService();
  late DeepgramLiveTranscriber _transcriber;

  var prefs = SharedPreferencesUtil();
  late List<Plugin> plugins;

  final scaffoldKey = GlobalKey<ScaffoldState>();
  bool loading = false;
  bool voiceEnabled = false;
  bool voiceActive = false;
  List<String> isFinals = [];

  Plugin? _activePlugin;

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
    plugins = prefs.pluginsList;
    SchedulerBinding.instance.addPostFrameCallback((_) {
      _moveListToBottom();
    });
    _initDailySummary();
    if (MessageProvider().getMessagesCount() == 0) {
      sendInitialPluginMessage(null);
    } else {
      String? pluginId = SharedPreferencesUtil().selectedChatPluginId ==
          'no_selected'
          ? null
          : SharedPreferencesUtil().selectedChatPluginId;
      _activePlugin = plugins.firstWhereOrNull((e) => e.id == pluginId);
      if (_activePlugin?.worksWithVoice() == true) {
        setState(() {
          voiceEnabled = true;
        });
        deepgramService.init();
      } else {
        setState(() {
          voiceEnabled = false;
        });
        deepgramService.stopTranscribing();
      }
    }
    super.initState();
  }

  void _onMicPressed() async {
    if (_activePlugin?.worksWithVoice() == true) {
      if(voiceActive) {
        _stopRecording();
        setState(() {
          voiceActive = false;
        });
      } else {
        _transcriber = await deepgramService.startTranscribing(_activePlugin?.voice?.listen.model,
            _activePlugin?.voice?.listen.endpointing);
        _transcriber.stream.listen((res) {
          String type = res.map['type'];
          if(type == 'Results') {
            // print('Deepgram Websocket: $type');
            if (res.map['is_final'] == true && res.transcript != '') {
              isFinals.add(res.transcript);
              if (res.map['speech_final'] == true && isFinals.isNotEmpty) {
                textController.text = isFinals.join(' ');
                _sendMessageUtil(textController.text);
                isFinals = [];
              }
            } else {
              textController.text =
              '${isFinals.join(' ')} ${res.transcript} ';
            }
          } else if(type == 'UtteranceEnd') {
            print('Deepgram Websocket: $type');
            if(isFinals.isNotEmpty) {
              textController.text = isFinals.join(' ');
              _sendMessageUtil(textController.text);
              isFinals = [];
            }
          } else {
            print('Deepgram Websocket: Unhandled Type: $type');
          }
        });

        setState(() {
          voiceActive = true;
        });
      }
    }
  }

  Future<void> _stopRecording() async {
    if(_activePlugin?.worksWithVoice() == true) {
      await deepgramService.stopTranscribing();
    }
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
              double topPadding = chatIndex == 0 ? 24 : 16;
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
                  pluginSender: plugins.firstWhereOrNull((e) => e.id == message.pluginId),
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
                prefixIcon: voiceEnabled
                    ? IconButton(
                  icon: Icon(
                    Icons.mic,
                    color: voiceActive ? Colors.green : Colors.grey.shade800,
                  ),
                  onPressed: _onMicPressed,
                ) : const SizedBox.shrink(),
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
    String? pluginId = SharedPreferencesUtil().selectedChatPluginId == 'no_selected'
        ? null
        : SharedPreferencesUtil().selectedChatPluginId;

    Message aiMessage = await _prepareStreaming(message, pluginId: pluginId);
    dynamic ragInfo = await retrieveRAGContext(message, prevMessagesPluginId: pluginId);
    String ragContext = ragInfo[0];
    List<Memory> memories = ragInfo[1].cast<Memory>();
    debugPrint('RAG Context: $ragContext memories: ${memories.length}');
    MixpanelManager().chatMessageSent(message);
    var prompt = qaRagPrompt(
      ragContext,
      await MessageProvider().retrieveMostRecentMessages(limit: 10, pluginId: pluginId),
      plugin: _activePlugin,
    );
    await streamApiResponse(
      prompt,
      _callbackFunctionChatStreaming(aiMessage),
          () async {
        aiMessage.memories.addAll(memories);
        MessageProvider().updateMessage(aiMessage);
        widget.refreshMessages();

        // If the plugin supports voice play the message
        if(_activePlugin?.worksWithVoice() == true) {
          deepgramService.pauseStream();
          await deepgramService.playTTS(aiMessage.text, _activePlugin?.voice?.speak.model);
          deepgramService.resumeStream();
        }

        if (memories.isNotEmpty) _moveListToBottom(extra: (70 * memories.length).toDouble());
      },
    );
    changeLoadingState();
  }

  sendInitialPluginMessage(Plugin? plugin) async {
    changeLoadingState();
    var ai = Message(DateTime.now(), '', 'ai', pluginId: plugin?.id);
    MessageProvider().saveMessage(ai);
    widget.messages.add(ai);
    _moveListToBottom();
    streamApiResponse(
      await getInitialPluginPrompt(plugin),
      _callbackFunctionChatStreaming(ai),
          () {
        MessageProvider().updateMessage(ai);
        widget.refreshMessages();
        // If the plugin supports voice play the message
        if(_activePlugin?.worksWithVoice() == true) {
          deepgramService.playTTS(ai.text, _activePlugin?.voice?.speak.model);
        }
      },
    );

    String? pluginId = SharedPreferencesUtil().selectedChatPluginId == 'no_selected'
        ? null
        : SharedPreferencesUtil().selectedChatPluginId;
    _activePlugin = plugins.firstWhereOrNull((e) => e.id == pluginId);
    if(_activePlugin?.worksWithVoice() == true) {
      setState(() {
        voiceEnabled = true;
      });
      deepgramService.init();
    } else {
      setState(() {
        voiceEnabled = false;
      });
      deepgramService.stopTranscribing();
    }

    changeLoadingState();
  }

  _prepareStreaming(String text, {String? pluginId}) async {
    textController.clear(); // setState if isolated
    var human = Message(DateTime.now(), text, 'human');
    var ai = Message(DateTime.now(), '', 'ai', pluginId: pluginId);
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
