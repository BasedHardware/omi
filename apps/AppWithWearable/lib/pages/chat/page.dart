import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/api_requests/stream_api_response.dart';
import 'package:friend_private/backend/mixpanel.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/backend/storage/message.dart';
import 'package:friend_private/flutter_flow/custom_functions.dart';
import 'package:friend_private/pages/chat/widgets/ai_message.dart';
import 'package:friend_private/pages/chat/widgets/user_message.dart';
import 'package:friend_private/widgets/blur_bot_widget.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:uuid/uuid.dart';

import '../../flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';

class ChatPage extends StatefulWidget {
  const ChatPage({super.key});

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  TextEditingController textController = TextEditingController();
  ScrollController listViewController = ScrollController();
  final unFocusNode = FocusNode();

  List<Message> _messages = [];
  var prefs = SharedPreferencesUtil();

  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
    _messages = prefs.chatMessages;

    // On page load action.
    SchedulerBinding.instance.addPostFrameCallback((_) async {
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
    return GestureDetector(
      onTap: () => unFocusNode.canRequestFocus
          ? FocusScope.of(context).requestFocus(unFocusNode)
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
                      controller: listViewController,
                    ),
                  ),
                ),
                Padding(
                  padding: const EdgeInsetsDirectional.fromSTEB(12.0, 16.0, 12.0, 12.0),
                  child: Container(
                    width: double.infinity,
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
                    child: Padding(
                      padding: const EdgeInsetsDirectional.fromSTEB(20.0, 4.0, 10.0, 4.0),
                      child: Row(
                        mainAxisSize: MainAxisSize.max,
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Expanded(
                            child: SizedBox(
                              width: 300.0,
                              child: TextField(
                                controller: textController,
                                textCapitalization: TextCapitalization.sentences,
                                obscureText: false,
                                decoration: InputDecoration(
                                  hintText: 'Chat with memories...',
                                  hintStyle: FlutterFlowTheme.of(context).bodySmall.override(
                                        fontFamily: FlutterFlowTheme.of(context).bodySmallFamily,
                                        color: FlutterFlowTheme.of(context).primaryText,
                                        fontSize: 14.0,
                                        fontWeight: FontWeight.w500,
                                        useGoogleFonts: GoogleFonts.asMap()
                                            .containsKey(FlutterFlowTheme.of(context).bodySmallFamily),
                                      ),
                                  enabledBorder: const UnderlineInputBorder(
                                    borderSide: BorderSide(
                                      color: Color(0x00000000),
                                      width: 1.0,
                                    ),
                                    borderRadius: BorderRadius.only(
                                      topLeft: Radius.circular(4.0),
                                      topRight: Radius.circular(4.0),
                                    ),
                                  ),
                                  focusedBorder: const UnderlineInputBorder(
                                    borderSide: BorderSide(
                                      color: Color(0x00000000),
                                      width: 1.0,
                                    ),
                                    borderRadius: BorderRadius.only(
                                      topLeft: Radius.circular(4.0),
                                      topRight: Radius.circular(4.0),
                                    ),
                                  ),
                                  errorBorder: const UnderlineInputBorder(
                                    borderSide: BorderSide(
                                      color: Color(0x00000000),
                                      width: 1.0,
                                    ),
                                    borderRadius: BorderRadius.only(
                                      topLeft: Radius.circular(4.0),
                                      topRight: Radius.circular(4.0),
                                    ),
                                  ),
                                  focusedErrorBorder: const UnderlineInputBorder(
                                    borderSide: BorderSide(
                                      color: Color(0x00000000),
                                      width: 1.0,
                                    ),
                                    borderRadius: BorderRadius.only(
                                      topLeft: Radius.circular(4.0),
                                      topRight: Radius.circular(4.0),
                                    ),
                                  ),
                                ),
                                style: FlutterFlowTheme.of(context).bodyMedium.override(
                                      fontFamily: FlutterFlowTheme.of(context).bodyMediumFamily,
                                      color: FlutterFlowTheme.of(context).primaryText,
                                      fontWeight: FontWeight.w500,
                                      useGoogleFonts: GoogleFonts.asMap()
                                          .containsKey(FlutterFlowTheme.of(context).bodyMediumFamily),
                                    ),
                                maxLines: 8,
                                minLines: 1,
                                keyboardType: TextInputType.multiline,
                                // FIXME
                                // validator: model.textControllerValidator.asValidator(context),
                              ),
                            ),
                          ),
                          FlutterFlowIconButton(
                            borderColor: Colors.transparent,
                            borderRadius: 30.0,
                            borderWidth: 1.0,
                            buttonSize: 60.0,
                            icon: const Icon(
                              Icons.send_rounded,
                              color: Color(0xFFF7F4F4),
                              size: 30.0,
                            ),
                            showLoadingIndicator: true,
                            onPressed: () async {
                              String message = textController.text;
                              if (message.isEmpty) return;
                              _prepareStreaming(message);
                              String ragContext = await _retrieveRAGContext(message);
                              debugPrint('RAG Context: $ragContext');
                              MixpanelManager().chatMessageSent(message);
                              await streamApiResponse(ragContext, _callbackFunctionChatStreaming(), _messages, () {
                                prefs.chatMessages = _messages;
                              });
                            },
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
              ],
            ),
          ],
        ),
      ),
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
