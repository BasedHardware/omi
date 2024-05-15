import 'package:friend_private/backend/api_requests/api_calls.dart';
import 'package:friend_private/backend/api_requests/stream_api_response.dart';
import 'package:friend_private/backend/storage/memories.dart';
import 'package:friend_private/backend/storage/vector_db.dart';
import 'package:friend_private/flutter_flow/custom_functions.dart';
import 'package:friend_private/widgets/blur_bot_widget.dart';

import '/flutter_flow/flutter_flow_icon_button.dart';
import '/flutter_flow/flutter_flow_theme.dart';
import '/flutter_flow/flutter_flow_util.dart';
import '/flutter_flow/flutter_flow_widgets.dart';
import 'dart:ui';
import '/flutter_flow/custom_functions.dart' as functions;
import 'package:auto_size_text/auto_size_text.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:provider/provider.dart';
import 'model.dart';
export 'model.dart';

class ChatPage extends StatefulWidget {
  const ChatPage({super.key});

  @override
  State<ChatPage> createState() => _ChatPageState();
}

class _ChatPageState extends State<ChatPage> {
  late ChatModel _model;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  void initState() {
    super.initState();
    _model = createModel(context, () => ChatModel());

    // On page load action.
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      await _model.listViewController?.animateTo(
        _model.listViewController!.position.maxScrollExtent,
        duration: const Duration(milliseconds: 100),
        curve: Curves.ease,
      );
      await _model.listViewController?.animateTo(
        _model.listViewController!.position.maxScrollExtent,
        duration: const Duration(milliseconds: 100),
        curve: Curves.ease,
      );
    });

    _model.textController ??= TextEditingController();
    _model.textFieldFocusNode ??= FocusNode();

    WidgetsBinding.instance.addPostFrameCallback((_) => setState(() {}));
  }

  @override
  void dispose() {
    _model.dispose();

    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    context.watch<FFAppState>();

    return GestureDetector(
      onTap: () => _model.unfocusNode.canRequestFocus
          ? FocusScope.of(context).requestFocus(_model.unfocusNode)
          : FocusScope.of(context).unfocus(),
      child: Scaffold(
        key: scaffoldKey,
        backgroundColor: FlutterFlowTheme.of(context).primary,
        appBar: AppBar(
          backgroundColor: FlutterFlowTheme.of(context).primary,
          automaticallyImplyLeading: false,
          title: Row(
            mainAxisSize: MainAxisSize.max,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              FFButtonWidget(
                onPressed: () async {
                  context.safePop();
                },
                text: '',
                icon: const Icon(
                  Icons.arrow_back_rounded,
                  size: 24.0,
                ),
                options: FFButtonOptions(
                  width: 44.0,
                  height: 44.0,
                  padding: const EdgeInsetsDirectional.fromSTEB(8.0, 0.0, 0.0, 0.0),
                  iconPadding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 0.0),
                  color: const Color(0x1AF7F4F4),
                  textStyle: FlutterFlowTheme.of(context).titleSmall.override(
                        fontFamily: FlutterFlowTheme.of(context).titleSmallFamily,
                        color: Colors.white,
                        fontWeight: FontWeight.bold,
                        useGoogleFonts: GoogleFonts.asMap().containsKey(FlutterFlowTheme.of(context).titleSmallFamily),
                      ),
                  elevation: 3.0,
                  borderSide: const BorderSide(
                    color: Colors.transparent,
                    width: 1.0,
                  ),
                  borderRadius: BorderRadius.circular(24.0),
                ),
              ),
              const Text('Chat'),
              const SizedBox(width: 32),
            ],
          ),
          actions: const [],
          centerTitle: false,
          toolbarHeight: 66.0,
          elevation: 2.0,
        ),
        body: Stack(
          children: [
            const BlurBotWidget(),
            SingleChildScrollView(
              controller: _model.columnController,
              child: Column(
                mainAxisSize: MainAxisSize.max,
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  SizedBox(
                    width: double.infinity,
                    height: MediaQuery.sizeOf(context).height * 0.8,
                    child: Padding(
                      padding: const EdgeInsetsDirectional.fromSTEB(0.0, 0.0, 0.0, 3.0),
                      child: Column(
                        mainAxisSize: MainAxisSize.max,
                        mainAxisAlignment: MainAxisAlignment.end,
                        children: [
                          Expanded(
                            child: Align(
                              alignment: const AlignmentDirectional(0.0, -1.0),
                              child: Padding(
                                padding: const EdgeInsetsDirectional.fromSTEB(0.0, 12.0, 0.0, 0.0),
                                child: Column(
                                  mainAxisSize: MainAxisSize.max,
                                  mainAxisAlignment: MainAxisAlignment.end,
                                  children: [
                                    Expanded(
                                      child: Padding(
                                        padding: const EdgeInsetsDirectional.fromSTEB(12.0, 12.0, 12.0, 0.0),
                                        child: ClipRRect(
                                          borderRadius: BorderRadius.circular(12.0),
                                          child: BackdropFilter(
                                            filter: ImageFilter.blur(
                                              sigmaX: 5.0,
                                              sigmaY: 4.0,
                                            ),
                                            child: Container(
                                              width: double.infinity,
                                              decoration: BoxDecoration(
                                                color: const Color(0x00151619),
                                                borderRadius: BorderRadius.circular(6.0),
                                                border: Border.all(
                                                  color: const Color(0x00E0E3E7),
                                                ),
                                              ),
                                              child: Align(
                                                alignment: const AlignmentDirectional(0.0, 1.0),
                                                child: Builder(
                                                  builder: (context) {
                                                    final chat = FFAppState().chatHistory.toList().take(100).toList();
                                                    return ListView.builder(
                                                      padding: EdgeInsets.zero,
                                                      shrinkWrap: true,
                                                      scrollDirection: Axis.vertical,
                                                      itemCount: chat.length,
                                                      itemBuilder: (context, chatIndex) {
                                                        final chatItem = chat[chatIndex];
                                                        // debugPrint('chatItem: $chatItem');
                                                        return Padding(
                                                          padding:
                                                              const EdgeInsetsDirectional.fromSTEB(0.0, 12.0, 0.0, 0.0),
                                                          child: Column(
                                                            mainAxisSize: MainAxisSize.max,
                                                            crossAxisAlignment: CrossAxisAlignment.start,
                                                            children: [
                                                              if (functions.stringContainsString(
                                                                      getJsonField(
                                                                        chatItem,
                                                                        r'''$.role''',
                                                                      ).toString(),
                                                                      'assistant') ??
                                                                  true)
                                                                Row(
                                                                  mainAxisSize: MainAxisSize.max,
                                                                  children: [
                                                                    Column(
                                                                      mainAxisSize: MainAxisSize.max,
                                                                      crossAxisAlignment: CrossAxisAlignment.start,
                                                                      children: [
                                                                        Container(
                                                                          constraints: BoxConstraints(
                                                                            maxWidth: () {
                                                                              if (MediaQuery.sizeOf(context).width >=
                                                                                  1170.0) {
                                                                                return 700.0;
                                                                              } else if (MediaQuery.sizeOf(context)
                                                                                      .width <=
                                                                                  470.0) {
                                                                                return 330.0;
                                                                              } else {
                                                                                return 530.0;
                                                                              }
                                                                            }(),
                                                                          ),
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
                                                                            border: Border.all(
                                                                              color:
                                                                                  FlutterFlowTheme.of(context).primary,
                                                                              width: 1.0,
                                                                            ),
                                                                          ),
                                                                          child: Padding(
                                                                            padding: const EdgeInsets.all(12.0),
                                                                            child: Column(
                                                                              mainAxisSize: MainAxisSize.min,
                                                                              crossAxisAlignment:
                                                                                  CrossAxisAlignment.start,
                                                                              children: [
                                                                                SelectionArea(
                                                                                    child: AutoSizeText(
                                                                                  getJsonField(
                                                                                    chatItem,
                                                                                    r'''$['content']''',
                                                                                  ).toString(),
                                                                                  style: FlutterFlowTheme.of(context)
                                                                                      .titleMedium
                                                                                      .override(
                                                                                        fontFamily:
                                                                                            FlutterFlowTheme.of(context)
                                                                                                .titleMediumFamily,
                                                                                        color:
                                                                                            FlutterFlowTheme.of(context)
                                                                                                .secondary,
                                                                                        fontSize: 14.0,
                                                                                        fontWeight: FontWeight.w500,
                                                                                        useGoogleFonts: GoogleFonts
                                                                                                .asMap()
                                                                                            .containsKey(
                                                                                                FlutterFlowTheme.of(
                                                                                                        context)
                                                                                                    .titleMediumFamily),
                                                                                        lineHeight: 1.5,
                                                                                      ),
                                                                                )),
                                                                              ],
                                                                            ),
                                                                          ),
                                                                        ),
                                                                        Padding(
                                                                          padding: const EdgeInsetsDirectional.fromSTEB(
                                                                              0.0, 6.0, 0.0, 0.0),
                                                                          child: InkWell(
                                                                            splashColor: Colors.transparent,
                                                                            focusColor: Colors.transparent,
                                                                            hoverColor: Colors.transparent,
                                                                            highlightColor: Colors.transparent,
                                                                            onTap: () async {
                                                                              await Clipboard.setData(ClipboardData(
                                                                                  text: getJsonField(
                                                                                chatItem,
                                                                                r'''$['content']''',
                                                                              ).toString()));
                                                                              ScaffoldMessenger.of(context)
                                                                                  .showSnackBar(
                                                                                SnackBar(
                                                                                  content: Text(
                                                                                    'Response copied to clipboard.',
                                                                                    style: FlutterFlowTheme.of(context)
                                                                                        .bodyMedium
                                                                                        .override(
                                                                                          fontFamily:
                                                                                              FlutterFlowTheme.of(
                                                                                                      context)
                                                                                                  .bodyMediumFamily,
                                                                                          color:
                                                                                              const Color(0x00000000),
                                                                                          fontSize: 12.0,
                                                                                          useGoogleFonts: GoogleFonts
                                                                                                  .asMap()
                                                                                              .containsKey(
                                                                                                  FlutterFlowTheme.of(
                                                                                                          context)
                                                                                                      .bodyMediumFamily),
                                                                                        ),
                                                                                  ),
                                                                                  duration: const Duration(
                                                                                      milliseconds: 2000),
                                                                                  backgroundColor:
                                                                                      FlutterFlowTheme.of(context)
                                                                                          .secondary,
                                                                                ),
                                                                              );
                                                                            },
                                                                            child: Row(
                                                                              mainAxisSize: MainAxisSize.max,
                                                                              children: [
                                                                                Padding(
                                                                                  padding: const EdgeInsetsDirectional
                                                                                      .fromSTEB(0.0, 0.0, 4.0, 0.0),
                                                                                  child: Icon(
                                                                                    Icons.content_copy,
                                                                                    color: FlutterFlowTheme.of(context)
                                                                                        .primary,
                                                                                    size: 10.0,
                                                                                  ),
                                                                                ),
                                                                                Text(
                                                                                  'Copy response',
                                                                                  style: FlutterFlowTheme.of(context)
                                                                                      .bodyMedium
                                                                                      .override(
                                                                                        fontFamily:
                                                                                            FlutterFlowTheme.of(context)
                                                                                                .bodyMediumFamily,
                                                                                        color:
                                                                                            FlutterFlowTheme.of(context)
                                                                                                .primary,
                                                                                        fontSize: 10.0,
                                                                                        useGoogleFonts: GoogleFonts
                                                                                                .asMap()
                                                                                            .containsKey(
                                                                                                FlutterFlowTheme.of(
                                                                                                        context)
                                                                                                    .bodyMediumFamily),
                                                                                      ),
                                                                                ),
                                                                              ],
                                                                            ),
                                                                          ),
                                                                        ),
                                                                      ],
                                                                    ),
                                                                  ],
                                                                ),
                                                              if (functions.stringContainsString(
                                                                      getJsonField(
                                                                        chatItem,
                                                                        r'''$.role''',
                                                                      ).toString(),
                                                                      'user') ??
                                                                  true)
                                                                Row(
                                                                  mainAxisSize: MainAxisSize.max,
                                                                  mainAxisAlignment: MainAxisAlignment.end,
                                                                  children: [
                                                                    Container(
                                                                      constraints: BoxConstraints(
                                                                        maxWidth: () {
                                                                          if (MediaQuery.sizeOf(context).width >=
                                                                              1170.0) {
                                                                            return 700.0;
                                                                          } else if (MediaQuery.sizeOf(context).width <=
                                                                              470.0) {
                                                                            return 330.0;
                                                                          } else {
                                                                            return 530.0;
                                                                          }
                                                                        }(),
                                                                      ),
                                                                      decoration: BoxDecoration(
                                                                        color: FlutterFlowTheme.of(context)
                                                                            .primaryBackground,
                                                                        borderRadius: BorderRadius.circular(12.0),
                                                                      ),
                                                                      child: Padding(
                                                                        padding: const EdgeInsets.all(12.0),
                                                                        child: Column(
                                                                          mainAxisSize: MainAxisSize.min,
                                                                          crossAxisAlignment: CrossAxisAlignment.start,
                                                                          children: [
                                                                            Text(
                                                                              getJsonField(
                                                                                chatItem,
                                                                                r'''$['content']''',
                                                                              ).toString(),
                                                                              style: FlutterFlowTheme.of(context)
                                                                                  .bodyMedium
                                                                                  .override(
                                                                                    fontFamily:
                                                                                        FlutterFlowTheme.of(context)
                                                                                            .bodyMediumFamily,
                                                                                    color: FlutterFlowTheme.of(context)
                                                                                        .primary,
                                                                                    fontWeight: FontWeight.w500,
                                                                                    useGoogleFonts: GoogleFonts.asMap()
                                                                                        .containsKey(
                                                                                            FlutterFlowTheme.of(context)
                                                                                                .bodyMediumFamily),
                                                                                  ),
                                                                            ),
                                                                          ],
                                                                        ),
                                                                      ),
                                                                    ),
                                                                  ],
                                                                ),
                                                            ],
                                                          ),
                                                        );
                                                      },
                                                      controller: _model.listViewController,
                                                    );
                                                  },
                                                ),
                                              ),
                                            ),
                                          ),
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                          ),
                          Column(
                            mainAxisSize: MainAxisSize.max,
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              const SizedBox(height: 4),
                              Container(
                                decoration: const BoxDecoration(),
                                child: Padding(
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
                                              child: TextFormField(
                                                controller: _model.textController,
                                                focusNode: _model.textFieldFocusNode,
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
                                                validator: _model.textControllerValidator.asValidator(context),
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
                                              String ragContext = await _retrieveRAGContext(_model.textController.text);
                                              await uiUpdatesChatQA();
                                              await streamApiResponse(
                                                ragContext,
                                                _callbackFunctionChatStreaming(),
                                              );

                                              setState(() {});
                                            },
                                          ),
                                        ],
                                      ),
                                    ),
                                  ),
                                ),
                              ),
                            ],
                          ),
                          if (responsiveVisibility(
                            context: context,
                            phone: false,
                            tablet: false,
                          ))
                            Container(
                              width: 100.0,
                              height: 60.0,
                              decoration: const BoxDecoration(),
                            ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<String> _retrieveRAGContext(String message) async {
    String? betterContextQuestion =
        await determineRequiresContext(message, retrieveMostRecentMessages(FFAppState().chatHistory));
    debugPrint('_retrieveRAGContext betterContextQuestion: $betterContextQuestion');
    if (betterContextQuestion == null) {
      return '';
    }
    List<double> vectorizedMessage = await getEmbeddingsFromInput(
      message,
    );
    List<String> memoriesId = querySimilarVectors(vectorizedMessage);
    debugPrint('querySimilarVectors memories retrieved: $memoriesId');
    if (memoriesId.isEmpty) {
      return '';
    }
    List<MemoryRecord> memories = await MemoryStorage.getAllMemoriesByIds(memoriesId);
    return MemoryRecord.memoriesToString(memories);
  }

  uiUpdatesChatQA() async {
    setState(() {
      FFAppState().chatHistory = functions.saveChatHistory(
          FFAppState().chatHistory, functions.convertToJSONRole(_model.textController.text, 'user')!)!;
    });
    await _model.listViewController?.animateTo(
      _model.listViewController!.position.maxScrollExtent,
      duration: const Duration(milliseconds: 100),
      curve: Curves.ease,
    );
    setState(() {
      _model.textController?.clear();
    });
  }

  _callbackFunctionChatStreaming() {
    return (String content) async {
      var chatHistory = FFAppState().chatHistory;
      var newChatHistory =
          appendToChatHistoryAtIndex(convertToJSONRole(content, "assistant"), chatHistory.length - 1, chatHistory);
      FFAppState().update(() {
        FFAppState().chatHistory = newChatHistory;
      });
      setState(() {});
      await _model.listViewController?.animateTo(
        _model.listViewController!.position.maxScrollExtent,
        duration: const Duration(milliseconds: 100),
        curve: Curves.ease,
      );
    };
  }
}
