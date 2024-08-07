import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/scheduler.dart';
import 'package:friend_private/backend/http/api/messages.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/memory.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/backend/schema/plugin.dart';
import 'package:friend_private/pages/chat/widgets/ai_message.dart';
import 'package:friend_private/pages/chat/widgets/user_message.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:uuid/uuid.dart';

class ChatPage extends StatefulWidget {
  final FocusNode textFieldFocusNode;
  final List<ServerMessage> messages;
  final Function(ServerMessage) addMessage;
  final Function(ServerMemory) updateMemory;

  const ChatPage({
    super.key,
    required this.textFieldFocusNode,
    required this.messages,
    required this.addMessage,
    required this.updateMemory,
  });

  @override
  State<ChatPage> createState() => ChatPageState();
}

class ChatPageState extends State<ChatPage> with AutomaticKeepAliveClientMixin {
  TextEditingController textController = TextEditingController();
  ScrollController scrollController = ScrollController();

  var prefs = SharedPreferencesUtil();
  late List<Plugin> plugins;

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
    plugins = prefs.pluginsList;
    SchedulerBinding.instance.addPostFrameCallback((_) {
      _moveListToBottom();
    });
    // _initDailySummary();
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
            reverse: true,
            physics: const NeverScrollableScrollPhysics(),
            itemCount: widget.messages.length,
            itemBuilder: (context, chatIndex) {
              final message = widget.messages[chatIndex];
              double topPadding = chatIndex == widget.messages.length - 1 ? 24 : 16;
              double bottomPadding = chatIndex == 0 ? (widget.textFieldFocusNode.hasFocus ? 120 : 200) : 0;
              return Padding(
                key: ValueKey(message.id),
                padding: EdgeInsets.only(bottom: bottomPadding, left: 18, right: 18, top: topPadding),
                child: message.sender == MessageSender.ai
                    ? AIMessage(
                        message: message,
                        sendMessage: _sendMessageUtil,
                        displayOptions: widget.messages.length <= 1,
                        pluginSender: plugins.firstWhereOrNull((e) => e.id == message.pluginId),
                        updateMemory: widget.updateMemory,
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
    String? pluginId = SharedPreferencesUtil().selectedChatPluginId == 'no_selected'
        ? null
        : SharedPreferencesUtil().selectedChatPluginId;
    widget.addMessage(
      ServerMessage(const Uuid().v4(), DateTime.now(), message, MessageSender.human, MessageType.text, null, false, []),
    );
    _moveListToBottom(extra: widget.textFieldFocusNode.hasFocus ? 148 : 200);
    textController.clear();
    ServerMessage aiMessage = await sendMessageServer(message, pluginId: pluginId);
    // TODO: restore streaming capabilities, with initial empty message
    debugPrint('aiMessage: ${aiMessage.id}: ${aiMessage.text}');
    widget.addMessage(aiMessage);
    _moveListToBottom(extra: widget.textFieldFocusNode.hasFocus ? 148 : 200);
    changeLoadingState();
  }

  sendInitialPluginMessage(Plugin? plugin) async {
    changeLoadingState();
    _moveListToBottom(extra: widget.textFieldFocusNode.hasFocus ? 148 : 200);
    ServerMessage message = await getInitialPluginMessage(plugin?.id);
    widget.addMessage(message);
    _moveListToBottom(extra: widget.textFieldFocusNode.hasFocus ? 148 : 200);
    changeLoadingState();
  }

  _moveListToBottom({double extra = 0}) async {
    try {
      scrollController.jumpTo(scrollController.position.maxScrollExtent + extra);
    } catch (e) {
      debugPrint(e.toString());
    }
  }
}
