import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:friend_private/backend/http/api/messages.dart';
import 'package:friend_private/backend/preferences.dart';
import 'package:friend_private/backend/schema/app.dart';
import 'package:friend_private/backend/schema/conversation.dart';
import 'package:friend_private/backend/schema/message.dart';
import 'package:friend_private/pages/chat/widgets/ai_message.dart';
import 'package:friend_private/pages/chat/widgets/animated_mini_banner.dart';
import 'package:friend_private/pages/chat/widgets/user_message.dart';
import 'package:friend_private/providers/connectivity_provider.dart';
import 'package:friend_private/providers/home_provider.dart';
import 'package:friend_private/providers/conversation_provider.dart';
import 'package:friend_private/providers/message_provider.dart';
import 'package:friend_private/utils/analytics/mixpanel.dart';
import 'package:friend_private/widgets/dialog.dart';
import 'package:friend_private/widgets/extensions/string.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:uuid/uuid.dart';

import 'widgets/message_action_menu.dart';

class ChatPage extends StatefulWidget {
  const ChatPage({
    super.key,
  });

  @override
  State<ChatPage> createState() => ChatPageState();
}

class ChatPageState extends State<ChatPage> with AutomaticKeepAliveClientMixin {
  TextEditingController textController = TextEditingController();
  late ScrollController scrollController;

  bool _showDeleteOption = false;
  bool isScrollingDown = false;

  bool _showSendButton = false;

  var prefs = SharedPreferencesUtil();
  late List<App> apps;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    apps = prefs.appsList;
    scrollController = ScrollController();
    scrollController.addListener(() {
      if (scrollController.position.userScrollDirection == ScrollDirection.reverse) {
        if (!isScrollingDown) {
          isScrollingDown = true;
          _showDeleteOption = true;
          setState(() {});
          Future.delayed(const Duration(seconds: 5), () {
            if (isScrollingDown) {
              isScrollingDown = false;
              _showDeleteOption = false;
              if (mounted) {
                setState(() {});
              }
            }
          });
        }
      }

      if (scrollController.position.userScrollDirection == ScrollDirection.forward) {
        if (isScrollingDown) {
          isScrollingDown = false;
          _showDeleteOption = false;
          setState(() {});
        }
      }
    });
    SchedulerBinding.instance.addPostFrameCallback((_) async {
      scrollToBottom();
    });
    super.initState();
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

    return Consumer2<MessageProvider, ConnectivityProvider>(
      builder: (context, provider, connectivityProvider, child) {
        return Scaffold(
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: provider.isLoadingMessages
              ? AnimatedMiniBanner(
                  showAppBar: provider.isLoadingMessages,
                  child: Container(
                    width: double.infinity,
                    height: 10,
                    color: Colors.green,
                    child: const Center(
                      child: Text(
                        'Syncing messages with server...',
                        style: TextStyle(color: Colors.white, fontSize: 14),
                      ),
                    ),
                  ),
                )
              : null,
          // AnimatedMiniBanner(
          //   showAppBar: _showDeleteOption,
          //   height: 80,
          //   child: Container(
          //     width: double.infinity,
          //     height: 40,
          //     color: Theme.of(context).primaryColor,
          //     child: Row(
          //       children: [
          //         const SizedBox(width: 20),
          //         const Spacer(),
          //         InkWell(
          //           onTap: () async {
          //             showDialog(
          //               context: context,
          //               builder: (ctx) {
          //                 return getDialog(context, () {
          //                   Navigator.of(context).pop();
          //                 }, () {
          //                   setState(() {
          //                     _showDeleteOption = false;
          //                   });
          //                   context.read<MessageProvider>().clearChat();
          //                   Navigator.of(context).pop();
          //                 }, "Clear Chat?",
          //                     "Are you sure you want to clear the chat? This action cannot be undone.");
          //               },
          //             );
          //           },
          //           child: const Padding(
          //             padding: EdgeInsets.all(8.0),
          //             child: Text(
          //               "Clear Chat  \u{1F5D1}",
          //               style: TextStyle(color: Colors.white, fontSize: 14),
          //             ),
          //           ),
          //         ),
          //         const SizedBox(width: 20),
          //       ],
          //     ),
          //   ),
          // ),
          body: Stack(
            children: [
              Align(
                alignment: Alignment.topCenter,
                child: provider.isLoadingMessages && !provider.hasCachedMessages
                    ? Column(
                        children: [
                          const SizedBox(height: 100),
                          const CircularProgressIndicator(
                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                          ),
                          const SizedBox(height: 16),
                          Text(
                            provider.firstTimeLoadingText,
                            style: const TextStyle(color: Colors.white),
                          ),
                        ],
                      )
                    : provider.isClearingChat
                        ? const Column(
                            children: [
                              SizedBox(height: 100),
                              CircularProgressIndicator(
                                valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                              ),
                              SizedBox(height: 16),
                              Text(
                                "Deleting your messages from Omi's memory...",
                                style: TextStyle(color: Colors.white),
                              ),
                            ],
                          )
                        : (provider.messages.isEmpty)
                            ? Center(
                                child: Padding(
                                  padding: const EdgeInsets.only(bottom: 32.0),
                                  child: Text(
                                      connectivityProvider.isConnected
                                          ? 'No messages yet!\nWhy don\'t you start a conversation?'
                                          : 'Please check your internet connection and try again',
                                      textAlign: TextAlign.center,
                                      style: const TextStyle(color: Colors.white)),
                                ),
                              )
                            : ListView.builder(
                                shrinkWrap: true,
                                reverse: true,
                                controller: scrollController,
                                //  physics: const NeverScrollableScrollPhysics(),
                                itemCount: provider.messages.length,
                                itemBuilder: (context, chatIndex) {
                                  final message = provider.messages[chatIndex];
                                  double topPadding = chatIndex == provider.messages.length - 1 ? 24 : 16;
                                  if (chatIndex != 0) message.askForNps = false;

                                  double bottomPadding = chatIndex == 0
                                      ? Platform.isAndroid
                                          ? 200
                                          : 170
                                      : 0;
                                  return GestureDetector(
                                    onLongPress: () {
                                      showModalBottomSheet(
                                        context: context,
                                        shape: const RoundedRectangleBorder(
                                          borderRadius: BorderRadius.vertical(
                                            top: Radius.circular(20),
                                          ),
                                        ),
                                        builder: (context) => MessageActionMenu(
                                          message: message.text.decodeString,
                                          onCopy: () async {
                                            await Clipboard.setData(ClipboardData(text: message.text.decodeString));
                                            ScaffoldMessenger.of(context).showSnackBar(
                                              const SnackBar(
                                                content: Text(
                                                  'Message copied to clipboard.',
                                                  style: TextStyle(
                                                    color: Color.fromARGB(255, 255, 255, 255),
                                                    fontSize: 12.0,
                                                  ),
                                                ),
                                                duration: Duration(milliseconds: 2000),
                                              ),
                                            );
                                            Navigator.pop(context);
                                          },
                                          onShare: () {
                                            MixpanelManager()
                                                .track('Chat Message Shared', properties: {'message': message.text});
                                            Share.share(
                                              '${message.text.decodeString}\n\nResponse from Omi. Get yours at https://omi.me',
                                              subject: 'Chat with Omi',
                                            );
                                            Navigator.pop(context);
                                          },
                                          onReport: () {
                                            if (message.sender == MessageSender.human) {
                                              Navigator.pop(context);
                                              ScaffoldMessenger.of(context).showSnackBar(
                                                const SnackBar(
                                                  content: Text(
                                                    'You cannot report your own messages.',
                                                    style: TextStyle(
                                                      color: Color.fromARGB(255, 255, 255, 255),
                                                      fontSize: 12.0,
                                                    ),
                                                  ),
                                                  duration: Duration(milliseconds: 2000),
                                                ),
                                              );
                                              return;
                                            }
                                            showDialog(
                                              context: context,
                                              builder: (context) {
                                                return getDialog(
                                                  context,
                                                  () {
                                                    Navigator.of(context).pop();
                                                  },
                                                  () {
                                                    Navigator.of(context).pop();
                                                    Navigator.of(context).pop();
                                                    context.read<MessageProvider>().removeLocalMessage(message.id);
                                                    reportMessageServer(message.id);
                                                    ScaffoldMessenger.of(context).showSnackBar(
                                                      const SnackBar(
                                                        content: Text(
                                                          'Message reported successfully.',
                                                          style: TextStyle(
                                                            color: Color.fromARGB(255, 255, 255, 255),
                                                            fontSize: 12.0,
                                                          ),
                                                        ),
                                                        duration: Duration(milliseconds: 2000),
                                                      ),
                                                    );
                                                  },
                                                  'Report Message',
                                                  'Are you sure you want to report this message?',
                                                );
                                              },
                                            );
                                            // Navigator.pop(context);
                                          },
                                        ),
                                      );
                                    },
                                    child: Padding(
                                      key: ValueKey(message.id),
                                      padding:
                                          EdgeInsets.only(bottom: bottomPadding, left: 18, right: 18, top: topPadding),
                                      child: message.sender == MessageSender.ai
                                          ? AIMessage(
                                              showTypingIndicator: provider.showTypingIndicator && chatIndex == 0,
                                              message: message,
                                              sendMessage: _sendMessageUtil,
                                              displayOptions: provider.messages.length <= 1,
                                              appSender: provider.messageSenderApp(message.appId),
                                              updateConversation: (ServerConversation conversation) {
                                                context.read<ConversationProvider>().updateConversation(conversation);
                                              },
                                              setMessageNps: (int value) {
                                                provider.setMessageNps(message, value);
                                              },
                                            )
                                          : HumanMessage(message: message),
                                    ),
                                  );
                                },
                              ),
              ),
              Consumer<HomeProvider>(builder: (context, home, child) {
                bool shouldShowSuffixIcon(MessageProvider p) {
                  return !p.sendingMessage && _showSendButton;
                }

                bool shouldShowSendButton(MessageProvider p) {
                  return !p.sendingMessage && _showSendButton;
                }

                return Align(
                  alignment: Alignment.bottomCenter,
                  child: Container(
                    width: double.maxFinite,
                    padding: EdgeInsets.only(left: 16, right: shouldShowSuffixIcon(provider) ? 4 : 16, bottom: 4),
                    margin: EdgeInsets.only(left: 20, right: 20, bottom: home.isChatFieldFocused ? 20 : 120),
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
                      focusNode: home.chatFieldFocusNode,
                      // canRequestFocus: true,
                      textAlign: TextAlign.start,
                      textAlignVertical: TextAlignVertical.center,
                      onChanged: (_) {
                        setShowSendButton();
                      },
                      decoration: InputDecoration(
                        hintText: 'Message',
                        hintStyle: const TextStyle(fontSize: 14.0, color: Colors.grey),
                        focusedBorder: InputBorder.none,
                        enabledBorder: InputBorder.none,
                        suffixIcon: shouldShowSuffixIcon(provider)
                            ? SizedBox(
                                width: 24,
                                height: 24,
                                child: shouldShowSendButton(provider)
                                    ? IconButton(
                                        splashColor: Colors.transparent,
                                        splashRadius: 1,
                                        onPressed: () async {
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
                                        icon: const Icon(
                                          Icons.arrow_upward_outlined,
                                          color: Color(0xFFF7F4F4),
                                          size: 20.0,
                                        ),
                                      )
                                    : const SizedBox.shrink(),
                              )
                            : null,
                      ),
                      maxLines: 8,
                      minLines: 1,
                      keyboardType: TextInputType.multiline,
                      style: TextStyle(fontSize: 14.0, color: Colors.grey.shade200, height: 24 / 14),
                    ),
                  ),
                );
              }),
            ],
          ),
        );
      },
    );
  }

  _sendMessageUtil(String text) async {
    var provider = context.read<MessageProvider>();
    MixpanelManager().chatMessageSent(text);
    provider.setSendingMessage(true);
    String? appId = provider.appProvider?.selectedChatAppId;
    if (appId == 'no_selected') {
      appId = null;
    }
    var message =
        ServerMessage(const Uuid().v4(), DateTime.now(), text, MessageSender.human, MessageType.text, appId, false, []);
    provider.addMessage(message);
    scrollToBottom();
    textController.clear();
    await provider.sendMessageStreamToServer(text, appId);
    scrollToBottom();
    provider.setSendingMessage(false);
  }

  sendInitialAppMessage(App? app) async {
    context.read<MessageProvider>().setSendingMessage(true);
    scrollToBottom();
    ServerMessage message = await getInitialAppMessage(app?.id);
    if (mounted) {
      context.read<MessageProvider>().addMessage(message);
    }
    scrollToBottom();
    context.read<MessageProvider>().setSendingMessage(false);
  }

  void _moveListToBottom() {
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

  scrollToBottom() => _moveListToBottom();
}
