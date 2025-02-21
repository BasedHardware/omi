import 'dart:io';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:friend_private/backend/http/api/messages.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/backend/schema/conversation.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/pages/chat/widgets/ai_message.dart';
import 'package:friend_private/pages/chat/widgets/user_message.dart';
import 'package:friend_private/pages/persona/persona_profile.dart';
import 'package:friend_private/pages/persona/persona_provider.dart';
import 'package:friend_private/providers/app_provider.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/providers/conversation_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/utils/other/temp.dart';
import 'package:provider/provider.dart';
import 'package:gradient_borders/gradient_borders.dart';

class CloneChatPage extends StatefulWidget {
  const CloneChatPage({
    super.key,
  });

  @override
  State<CloneChatPage> createState() => CloneChatPageState();
}

class CloneChatPageState extends State<CloneChatPage> with AutomaticKeepAliveClientMixin {
  TextEditingController textController = TextEditingController();
  late ScrollController scrollController;
  bool isScrollingDown = false;
  bool _showSendButton = false;
  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    scrollController = ScrollController();
    scrollController.addListener(_handleScroll);
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      final provider = Provider.of<PersonaProvider>(context, listen: false);
      await provider.getUserPersona();
      if (provider.userPersona != null) {
        var selectedApp = provider.userPersona!;
        var appProvider = context.read<AppProvider>();
        var messageProvider = context.read<MessageProvider>();
        appProvider.setSelectedChatAppId(selectedApp.id);
        await messageProvider.refreshMessages();
        if (messageProvider.messages.isEmpty) {
          messageProvider.sendInitialAppMessage(selectedApp);
        }
      }
      scrollToBottom();
    });
    super.initState();
  }

  void _handleScroll() {
    if (scrollController.position.userScrollDirection == ScrollDirection.reverse) {
      if (!isScrollingDown) {
        isScrollingDown = true;
        setState(() {});
        Future.delayed(const Duration(seconds: 5), () {
          if (isScrollingDown) {
            isScrollingDown = false;
            if (mounted) setState(() {});
          }
        });
      }
    }

    if (scrollController.position.userScrollDirection == ScrollDirection.forward) {
      if (isScrollingDown) {
        isScrollingDown = false;
        setState(() {});
      }
    }
  }

  @override
  void dispose() {
    textController.dispose();
    scrollController.dispose();
    super.dispose();
  }

  void setShowSendButton() {
    if (_showSendButton != textController.text.isNotEmpty) {
      setState(() {
        _showSendButton = textController.text.isNotEmpty;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);

    return Consumer3<MessageProvider, ConnectivityProvider, PersonaProvider>(
      builder: (context, provider, connectivityProvider, personaProvider, child) {
        return Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: AppBar(
            backgroundColor: Colors.transparent,
            elevation: 0,
            leading: GestureDetector(
                child: SizedBox(
                  width: 24,
                  height: 24,
                  child: Padding(
                    padding: const EdgeInsets.all(8.0),
                    child: SvgPicture.asset('assets/images/ic_clone_plus.svg'),
                  ),
                ),
                onTap: () {
                  routeToPage(context, const PersonaProfilePage(), replace: true);
                }),
            title: Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                CircleAvatar(
                  backgroundImage: NetworkImage(personaProvider.userPersona?.image ?? ''),
                  radius: 16,
                ),
                const SizedBox(
                  width: 24,
                )
              ],
            ),
          ),
          body: personaProvider.isLoading || personaProvider.userPersona == null || provider.isLoadingMessages
              ? const Center(
                  child: CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation(Colors.white),
                  ),
                )
              : GestureDetector(
                  onTap: () {
                    // Hide keyboard when tapping outside
                    FocusScope.of(context).unfocus();
                  },
                  child: Stack(
                    children: [
                      Align(
                        alignment: Alignment.topCenter,
                        child: provider.isLoadingMessages && !provider.hasCachedMessages
                            ? const _LoadingWidget()
                            : provider.messages.isEmpty
                                ? _EmptyChat(isConnected: connectivityProvider.isConnected)
                                : _MessageList(
                                    messages: provider.messages,
                                    controller: scrollController,
                                    showTypingIndicator: provider.showTypingIndicator,
                                    onSendMessage: _sendMessageUtil,
                                    provider: provider,
                                    app: personaProvider.userPersona!,
                                  ),
                      ),
                      _BottomInput(
                        textController: textController,
                        onTextChanged: setShowSendButton,
                        showSendButton: _showSendButton,
                        onSendMessage: () {
                          String message = textController.text;
                          if (message.isEmpty) return;
                          if (connectivityProvider.isConnected) {
                            _sendMessageUtil(message);
                          } else {
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(
                                content: Text('Please check your internet connection and try again'),
                                duration: Duration(seconds: 2),
                              ),
                            );
                          }
                        },
                      ),
                    ],
                  ),
                ),
        );
      },
    );
  }

  _sendMessageUtil(String text) {
    var provider = context.read<MessageProvider>();
    MixpanelManager().chatMessageSent(text);
    provider.setSendingMessage(true);
    provider.addMessageLocally(text);
    scrollToBottom();
    textController.clear();
    provider.sendMessageStreamToServer(text);
    provider.setSendingMessage(false);
  }

  void scrollToBottom() {
    SchedulerBinding.instance.addPostFrameCallback((_) {
      if (scrollController.hasClients) {
        scrollController.animateTo(
          0.0,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }
}

class _LoadingWidget extends StatelessWidget {
  const _LoadingWidget();

  @override
  Widget build(BuildContext context) {
    return const Column(
      children: [
        SizedBox(height: 100),
        CircularProgressIndicator(
          valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
        ),
        SizedBox(height: 16),
        Text(
          "Loading messages...",
          style: TextStyle(color: Colors.white),
        ),
      ],
    );
  }
}

class _EmptyChat extends StatelessWidget {
  final bool isConnected;

  const _EmptyChat({required this.isConnected});

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.only(bottom: 32.0),
        child: Text(
          isConnected
              ? 'No messages yet!\nWhy don\'t you start a conversation?'
              : 'Please check your internet connection and try again',
          textAlign: TextAlign.center,
          style: const TextStyle(color: Colors.white),
        ),
      ),
    );
  }
}

class _MessageList extends StatelessWidget {
  final List<ServerMessage> messages;
  final ScrollController controller;
  final bool showTypingIndicator;
  final Function(String) onSendMessage;
  final MessageProvider provider;
  final App app;

  const _MessageList({
    required this.messages,
    required this.controller,
    required this.showTypingIndicator,
    required this.onSendMessage,
    required this.provider,
    required this.app,
  });

  @override
  Widget build(BuildContext context) {
    return ListView.builder(
      shrinkWrap: true,
      reverse: true,
      controller: controller,
      itemCount: messages.length,
      itemBuilder: (context, index) {
        final message = messages[index];
        double topPadding = index == messages.length - 1 ? 24 : 16;
        double bottomPadding = index == 0
            ? Platform.isAndroid
                ? MediaQuery.sizeOf(context).height * 0.21
                : MediaQuery.sizeOf(context).height * 0.19
            : 0;

        return Padding(
          key: ValueKey(message.id),
          padding: EdgeInsets.only(
            bottom: bottomPadding,
            left: 18,
            right: 18,
            top: topPadding,
          ),
          child: message.sender == MessageSender.ai
              ? AIMessage(
                  showTypingIndicator: showTypingIndicator && index == 0,
                  message: message,
                  sendMessage: onSendMessage,
                  displayOptions: false,
                  appSender: app,
                  updateConversation: (ServerConversation conversation) {
                    context.read<ConversationProvider>().updateConversation(conversation);
                  },
                  setMessageNps: (int value) {
                    provider.setMessageNps(message, value);
                  },
                )
              : HumanMessage(message: message),
        );
      },
    );
  }
}

class _BottomInput extends StatelessWidget {
  final TextEditingController textController;
  final VoidCallback onTextChanged;
  final bool showSendButton;
  final VoidCallback onSendMessage;

  const _BottomInput({
    required this.textController,
    required this.onTextChanged,
    required this.showSendButton,
    required this.onSendMessage,
  });

  @override
  Widget build(BuildContext context) {
    return Consumer<HomeProvider>(
      builder: (context, home, child) {
        return Align(
          alignment: Alignment.bottomCenter,
          child: Container(
            width: double.maxFinite,
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            margin: const EdgeInsets.only(left: 28, right: 28, bottom: 40),
            decoration: const BoxDecoration(
              color: Colors.black,
              borderRadius: BorderRadius.all(Radius.circular(16)),
              border: GradientBoxBorder(
                gradient: LinearGradient(
                  colors: [
                    Color.fromARGB(127, 208, 208, 208),
                    Color.fromARGB(127, 188, 99, 121),
                    Color.fromARGB(127, 86, 101, 182),
                    Color.fromARGB(127, 126, 190, 236),
                  ],
                ),
                width: 1,
              ),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                const SizedBox(width: 12),
                Expanded(
                  child: ConstrainedBox(
                    constraints: const BoxConstraints(maxHeight: 150),
                    child: TextField(
                      controller: textController,
                      onChanged: (_) => onTextChanged(),
                      focusNode: home.chatFieldFocusNode,
                      decoration: const InputDecoration(
                        hintText: 'Message',
                        hintStyle: TextStyle(fontSize: 14.0, color: Colors.grey),
                        focusedBorder: InputBorder.none,
                        enabledBorder: InputBorder.none,
                        contentPadding: EdgeInsets.symmetric(vertical: 8),
                      ),
                      maxLines: null,
                      keyboardType: TextInputType.multiline,
                      style: TextStyle(
                        fontSize: 14.0,
                        color: Colors.grey.shade200,
                        height: 24 / 14,
                      ),
                    ),
                  ),
                ),
                if (showSendButton)
                  IconButton(
                    splashColor: Colors.transparent,
                    splashRadius: 1,
                    onPressed: onSendMessage,
                    icon: const Icon(
                      Icons.arrow_upward_outlined,
                      color: Color(0xFFF7F4F4),
                      size: 20.0,
                    ),
                  ),
              ],
            ),
          ),
        );
      },
    );
  }
}
