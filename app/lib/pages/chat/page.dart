import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/scheduler.dart';
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
import 'package:gradient_borders/gradient_borders.dart';
import 'package:provider/provider.dart';
import 'package:uuid/uuid.dart';

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
              : AnimatedMiniBanner(
                  showAppBar: _showDeleteOption,
                  height: 80,
                  child: Container(
                    width: double.infinity,
                    height: 40,
                    color: Theme.of(context).primaryColor,
                    child: Row(
                      children: [
                        const SizedBox(width: 20),
                        const Spacer(),
                        InkWell(
                          onTap: () async {
                            showDialog(
                              context: context,
                              builder: (ctx) {
                                return getDialog(context, () {
                                  Navigator.of(context).pop();
                                }, () {
                                  setState(() {
                                    _showDeleteOption = false;
                                  });
                                  context.read<MessageProvider>().clearChat();
                                  Navigator.of(context).pop();
                                }, "Clear Chat?",
                                    "Are you sure you want to clear the chat? This action cannot be undone.");
                              },
                            );
                          },
                          child: const Padding(
                            padding: EdgeInsets.all(8.0),
                            child: Text(
                              "Clear Chat  \u{1F5D1}",
                              style: TextStyle(color: Colors.white, fontSize: 14),
                            ),
                          ),
                        ),
                        const SizedBox(width: 20),
                      ],
                    ),
                  ),
                ),
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
                                  return Padding(
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
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: double.maxFinite,
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        margin: EdgeInsets.only(left: 28, right: 28, bottom: home.isChatFieldFocused ? 40 : 120),
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
                        child: Column(
                          children: [
                            Consumer<MessageProvider>(builder: (context, provider, child) {
                              if (provider.selectedFile != null) {
                                return Stack(
                                  children: [
                                    Align(
                                      alignment: Alignment.centerLeft,
                                      child: Container(
                                        margin: const EdgeInsets.only(bottom: 10, top: 10, left: 10),
                                        height: MediaQuery.sizeOf(context).width * 0.2,
                                        width: MediaQuery.sizeOf(context).width * 0.2,
                                        decoration: BoxDecoration(
                                          color: Colors.grey[800],
                                          image: provider.selectedFileType == 'image'
                                              ? DecorationImage(
                                                  image: FileImage(provider.selectedFile!),
                                                  fit: BoxFit.cover,
                                                )
                                              : null,
                                          borderRadius: BorderRadius.circular(10),
                                        ),
                                        child: Stack(
                                          children: [
                                            provider.selectedFileType != 'image'
                                                ? const Center(
                                                    child: Icon(
                                                      Icons.insert_drive_file,
                                                      color: Colors.white,
                                                      size: 30,
                                                    ),
                                                  )
                                                : Container(),
                                            Positioned(
                                              top: 5,
                                              right: 5,
                                              child: GestureDetector(
                                                onTap: () {
                                                  provider.clearSelectedFile();
                                                },
                                                child: CircleAvatar(
                                                  radius: 12,
                                                  backgroundColor: Colors.grey[700],
                                                  child: const Icon(Icons.close, size: 16, color: Colors.white),
                                                ),
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                  ],
                                );
                              } else {
                                return Container();
                              }
                            }),
                            Row(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                IconButton(
                                  icon: const Icon(
                                    Icons.add,
                                    color: Color(0xFFF7F4F4),
                                    size: 24.0,
                                  ),
                                  onPressed: () {
                                    showModalBottomSheet(
                                      context: context,
                                      backgroundColor: Colors.grey[850],
                                      shape: const RoundedRectangleBorder(
                                        borderRadius: BorderRadius.vertical(top: Radius.circular(16.0)),
                                      ),
                                      builder: (BuildContext context) {
                                        return Padding(
                                          padding: const EdgeInsets.fromLTRB(12, 12, 12, 40),
                                          child: Wrap(
                                            children: [
                                              ListTile(
                                                leading: const Icon(Icons.camera_alt, color: Colors.white),
                                                title:
                                                    const Text("Take a Photo", style: TextStyle(color: Colors.white)),
                                                onTap: () {
                                                  Navigator.pop(context);
                                                  context.read<MessageProvider>().takeImage();
                                                },
                                              ),
                                              ListTile(
                                                leading: const Icon(Icons.photo, color: Colors.white),
                                                title:
                                                    const Text("Select a Photo", style: TextStyle(color: Colors.white)),
                                                onTap: () {
                                                  Navigator.pop(context);
                                                  context.read<MessageProvider>().selectImage();
                                                },
                                              ),
                                              ListTile(
                                                leading: const Icon(Icons.insert_drive_file, color: Colors.white),
                                                title:
                                                    const Text("Select a File", style: TextStyle(color: Colors.white)),
                                                onTap: () {
                                                  Navigator.pop(context);
                                                  context.read<MessageProvider>().selectFile();
                                                },
                                              ),
                                            ],
                                          ),
                                        );
                                      },
                                    );
                                  },
                                ),
                                Expanded(
                                  child: ConstrainedBox(
                                    constraints: const BoxConstraints(
                                      maxHeight: 150,
                                    ),
                                    child: TextField(
                                      enabled: true,
                                      controller: textController,
                                      obscureText: false,
                                      focusNode: home.chatFieldFocusNode,
                                      textAlign: TextAlign.start,
                                      textAlignVertical: TextAlignVertical.top,
                                      decoration: const InputDecoration(
                                        hintText: 'Message',
                                        hintStyle: TextStyle(fontSize: 14.0, color: Colors.grey),
                                        focusedBorder: InputBorder.none,
                                        enabledBorder: InputBorder.none,
                                        contentPadding: EdgeInsets.only(top: 8, bottom: 8),
                                      ),
                                      maxLines: null,
                                          keyboardType: TextInputType.multiline,
                      style: TextStyle(fontSize: 14.0, color: Colors.grey.shade200, height: 24 / 14),
                                    ),
                                  ),
                                ),
                               !shouldShowSuffixIcon(provider) ? const SizedBox.shrink() : IconButton(
                                  splashColor: Colors.transparent,
                                  splashRadius: 1,
                                  onPressed: provider.sendingMessage
                                      ? null
                                      : () async {
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
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                );
              }),
            ],
          ),
        );
      },
    );
  }

  _sendMessageUtil(String message) async {
    MixpanelManager().chatMessageSent(message);
    var provider = context.read<MessageProvider>();
    provider.setSendingMessage(true);
    String? appId = provider.appProvider?.selectedChatAppId;
    if (appId == 'no_selected') {
      appId = null;
    }
    var newMessage = ServerMessage(
      const Uuid().v4(),
      DateTime.now(),
      message,
      MessageSender.human,
      MessageType.text,
      appId,
      false,
      [],
      files: provider.uploadedFile != null ? [provider.uploadedFile!] : [],
    );
    provider.addMessage(newMessage);
    scrollToBottom();
    textController.clear();
    provider.sendMessageToServer(message, appId);
    // TODO: restore streaming capabilities, with initial empty message
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
