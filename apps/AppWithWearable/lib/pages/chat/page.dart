import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/api_requests/stream_api_response.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/backend/storage/message.dart';
import 'package:friend_private/backend/storage/vector_db.dart';
import 'package:friend_private/flutter_flow/custom_functions.dart';
import 'package:friend_private/pages/chat/widgets/ai_message.dart';
import 'package:friend_private/pages/chat/widgets/text_field.dart';
import 'package:friend_private/pages/chat/widgets/user_message.dart';
import 'package:friend_private/widgets/blur_bot_widget.dart';
import 'package:uuid/uuid.dart';

import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'model.dart';
export 'model.dart';

class ChatPage extends StatefulWidget {
  const ChatPage({super.key});

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  late ChatModel _model;
  List<Message> _messages = [];
  var prefs = SharedPreferencesUtil();

  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => ChatModel());

    _model.textController ??= TextEditingController();
    _model.textFieldFocusNode ??= FocusNode();
    _messages = prefs.chatMessages;

    // On page load action.
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      _moveListToBottom(initial: true);
    });
  }

  @override
  void dispose() {
    _model.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: () => _model.unFocusNode.canRequestFocus
          ? FocusScope.of(context).requestFocus(_model.unFocusNode)
          : FocusScope.of(context).unfocus(),
      child: Scaffold(
        key: scaffoldKey,
        backgroundColor: FlutterFlowTheme.of(context).primary,
        // appBar: getChatAppBar(context),
        body: Stack(
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
                      controller: _model.listViewController,
                    ),
                  ),
                ),
                ChatTextField(
                    model: _model,
                    onSendPressed: () async {
                      String message = _model.textController.text;
                      if (message.isEmpty) return;
                      _prepareStreaming(message);
                      String ragContext = await _retrieveRAGContext(message);
                      debugPrint('RAG Context: $ragContext');
                      MixpanelManager().chatMessageSent(message);
                      await streamApiResponse(ragContext, _callbackFunctionChatStreaming(), _messages, () {
                        prefs.chatMessages = _messages;
                      });
                    }),
                const SizedBox(height: 16),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Future<String> _retrieveRAGContext(String message) async {
    String? betterContextQuestion = await determineRequiresContext(message, retrieveMostRecentMessages(_messages));
    debugPrint('_retrieveRAGContext betterContextQuestion: $betterContextQuestion');
    if (betterContextQuestion == null) {
      return '';
    }
    List<double> vectorizedMessage = await getEmbeddingsFromInput(
      message,
    );
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
      _model.textController?.clear();
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
    await _model.listViewController?.animateTo(
      _model.listViewController!.position.maxScrollExtent + (initial ? 100 : 0),
      duration: const Duration(milliseconds: 100),
      curve: Curves.ease,
    );
  }
}
