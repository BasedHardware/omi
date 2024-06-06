import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/api_requests/stream_api_response.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/backend/storage/message.dart';
import 'package:friend_private/pages/chat/widgets/ai_message.dart';
import 'package:friend_private/pages/chat/widgets/user_message.dart';
import 'package:friend_private/utils/temp.dart';
import 'package:friend_private/widgets/blur_bot_widget.dart';
import 'package:uuid/uuid.dart';

import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

class ChatPage extends StatefulWidget {
  final FocusNode textFieldFocusNode;

  const ChatPage({super.key, required this.textFieldFocusNode});

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
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
  void initState() {
    super.initState();
    _messages = prefs.chatMessages;
    SchedulerBinding.instance.addPostFrameCallback((_) => _moveListToBottom(initial: true));
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
        const BlurBotWidget(),
        Column(
          mainAxisSize: MainAxisSize.max,
          mainAxisAlignment: MainAxisAlignment.end,
          children: [
            Expanded(
              child: Container(
                padding: const EdgeInsets.fromLTRB(16, 16, 16, 0),
                child: ListView.builder(
                  scrollDirection: Axis.vertical,
                  itemCount: _messages.length,
                  itemBuilder: (context, chatIndex) {
                    final message = _messages[chatIndex];
                    if (message.type == 'ai') return AIMessage(message: message);
                    if (message.type == 'human') {
                      return HumanMessage(message: message);
                    }
                    return const SizedBox.shrink();
                  },
                  controller: listViewController,
                ),
              ),
            ),
            Container(
              width: double.infinity,
              padding: const EdgeInsetsDirectional.fromSTEB(20.0, 12, 10.0, 8),
              margin: const EdgeInsetsDirectional.fromSTEB(12.0, 16.0, 12.0, 12.0),
              decoration: BoxDecoration(
                color: const Color(0x1AF7F4F4),
                boxShadow: const [
                  BoxShadow(
                    blurRadius: 3.0,
                    color: Color(0x33000000),
                    offset: Offset(0.0, 1.0),
                  )
                ],
                borderRadius: BorderRadius.circular(12.0),
              ),
              child: SizedBox(
                width: 300.0,
                child: TextField(
                  onTap: () {
                    widget.textFieldFocusNode.requestFocus();
                  },
                  enabled: true,
                  controller: textController,
                  textCapitalization: TextCapitalization.sentences,
                  obscureText: false,
                  focusNode: widget.textFieldFocusNode,
                  canRequestFocus: true,
                  decoration: InputDecoration(
                      hintText: 'Chat with memories...',
                      hintStyle: TextStyle(fontSize: 14.0, color: Colors.grey.shade200),
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
                                changeLoadingState();
                                _prepareStreaming(message);
                                String ragContext = await _retrieveRAGContext(message);
                                debugPrint('RAG Context: $ragContext');
                                MixpanelManager().chatMessageSent(message);
                                await streamApiResponse(ragContext, _callbackFunctionChatStreaming(), _messages, () {
                                  prefs.chatMessages = _messages;
                                });
                                changeLoadingState();
                              },
                      )),
                  maxLines: 8,
                  minLines: 1,
                  keyboardType: TextInputType.multiline,
                  style: TextStyle(fontSize: 14.0, color: Colors.grey.shade200),
                ),
              ),
            ),
            const SizedBox(height: 16),
          ],
        ),
      ],
    );
  }

  Future<String> _retrieveRAGContext(String message) async {
    String? betterContextQuestion = await determineRequiresContext(retrieveMostRecentMessages(_messages));
    debugPrint('_retrieveRAGContext betterContextQuestion: $betterContextQuestion');
    if (betterContextQuestion == null) {
      return '';
    }
    List<double> vectorizedMessage = await getEmbeddingsFromInput(betterContextQuestion);
    List<String> memoriesId = await queryPineconeVectors(vectorizedMessage);
    debugPrint('queryPineconeVectors memories retrieved: $memoriesId');
    if (memoriesId.isEmpty) {
      return '';
    }
    List<MemoryRecord> memories = await MemoryStorage.getAllMemoriesByIds(memoriesId);
    return MemoryRecord.memoriesToString(memories);
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

  _callbackFunctionChatStreaming() {
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
    await listViewController.animateTo(
      listViewController.position.maxScrollExtent + (initial ? 100 : 0),
      duration: const Duration(milliseconds: 100),
      curve: Curves.ease,
    );
  }
}
