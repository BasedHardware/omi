import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/pages/chat/select_text_screen.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/pages/chat/widgets/animated_mini_banner.dart';
import 'package:omi/pages/chat/widgets/user_message.dart';
import 'package:omi/pages/chat/widgets/voice_recorder_widget.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:gradient_borders/gradient_borders.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import 'widgets/message_action_menu.dart';

class ChatPage extends StatefulWidget {
  final bool isPivotBottom;

  const ChatPage({
    super.key,
    this.isPivotBottom = false,
  });

  @override
  State<ChatPage> createState() => ChatPageState();
}

class ChatPageState extends State<ChatPage> with AutomaticKeepAliveClientMixin {
  TextEditingController textController = TextEditingController();
  late ScrollController scrollController;

  bool isScrollingDown = false;

  bool _showVoiceRecorder = false;

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
          setState(() {});
          Future.delayed(const Duration(seconds: 5), () {
            if (isScrollingDown) {
              isScrollingDown = false;
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
                                      ? provider.selectedFiles.isNotEmpty
                                          ? (Platform.isAndroid
                                              ? MediaQuery.sizeOf(context).height * 0.32
                                              : MediaQuery.sizeOf(context).height * 0.3)
                                          : (Platform.isAndroid
                                              ? MediaQuery.sizeOf(context).height * 0.21
                                              : MediaQuery.sizeOf(context).height * 0.19)
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
                                            MixpanelManager()
                                                .track('Chat Message Copied', properties: {'message': message.text});
                                            await Clipboard.setData(ClipboardData(text: message.text.decodeString));
                                            if (context.mounted) {
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
                                            }
                                          },
                                          onSelectText: () {
                                            MixpanelManager().track('Chat Message Text Selected',
                                                properties: {'message': message.text});
                                            routeToPage(context, SelectTextScreen(message: message));
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
                                                    MixpanelManager().track('Chat Message Reported',
                                                        properties: {'message': message.text});
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
                                              displayOptions: provider.messages.length <= 1 &&
                                                  provider.messageSenderApp(message.appId)?.isNotPersona() == true,
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
                bool shouldShowSendButton(MessageProvider p) {
                  return !p.sendingMessage && !_showVoiceRecorder;
                }

                bool shouldShowVoiceRecorderButton() {
                  return !_showVoiceRecorder;
                }

                bool shouldShowMenuButton() {
                  return !_showVoiceRecorder;
                }

                return Align(
                  alignment: Alignment.bottomCenter,
                  child: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: double.maxFinite,
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                        margin: EdgeInsets.only(
                            left: 28,
                            right: 28,
                            bottom: widget.isPivotBottom ? 40 : (home.isChatFieldFocused ? 40 : 120)),
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
                              if (provider.selectedFiles.isNotEmpty) {
                                return Stack(
                                  children: [
                                    Align(
                                      alignment: Alignment.centerLeft,
                                      child: SizedBox(
                                        height: MediaQuery.sizeOf(context).height * 0.118,
                                        child: ListView.builder(
                                          itemCount: provider.selectedFiles.length,
                                          scrollDirection: Axis.horizontal,
                                          shrinkWrap: true,
                                          itemBuilder: (ctx, idx) {
                                            return Container(
                                              margin: const EdgeInsets.only(bottom: 10, top: 10, left: 10),
                                              height: MediaQuery.sizeOf(context).width * 0.2,
                                              width: MediaQuery.sizeOf(context).width * 0.2,
                                              decoration: BoxDecoration(
                                                color: Colors.grey[800],
                                                image: provider.selectedFileTypes[idx] == 'image'
                                                    ? DecorationImage(
                                                        image: FileImage(provider.selectedFiles[idx]),
                                                        fit: BoxFit.cover,
                                                      )
                                                    : null,
                                                borderRadius: BorderRadius.circular(10),
                                              ),
                                              child: Stack(
                                                children: [
                                                  provider.selectedFileTypes[idx] != 'image'
                                                      ? const Center(
                                                          child: Icon(
                                                            Icons.insert_drive_file,
                                                            color: Colors.white,
                                                            size: 30,
                                                          ),
                                                        )
                                                      : Container(),
                                                  if (provider.isFileUploading(provider.selectedFiles[idx].path))
                                                    Container(
                                                      color: Colors.black.withOpacity(0.5),
                                                      child: const Center(
                                                        child: SizedBox(
                                                          width: 20,
                                                          height: 20,
                                                          child: CircularProgressIndicator(
                                                            valueColor: AlwaysStoppedAnimation<Color>(Colors.white70),
                                                          ),
                                                        ),
                                                      ),
                                                    ),
                                                  Positioned(
                                                    top: 4,
                                                    right: 4,
                                                    child: GestureDetector(
                                                      onTap: () {
                                                        provider.clearSelectedFile(idx);
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
                                            );
                                          },
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
                                if (shouldShowMenuButton())
                                  IconButton(
                                    icon: Icon(
                                      Icons.add,
                                      color: provider.selectedFiles.length > 3 ? Colors.grey : const Color(0xFFF7F4F4),
                                      size: 24.0,
                                    ),
                                    onPressed: () {
                                      if (provider.selectedFiles.length > 3) {
                                        ScaffoldMessenger.of(context).showSnackBar(
                                          const SnackBar(
                                            content: Text('You can only upload 4 files at a time'),
                                            duration: Duration(seconds: 2),
                                          ),
                                        );
                                        return;
                                      }
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
                                                    context.read<MessageProvider>().captureImage();
                                                  },
                                                ),
                                                ListTile(
                                                  leading: const Icon(Icons.photo, color: Colors.white),
                                                  title: const Text("Select a Photo",
                                                      style: TextStyle(color: Colors.white)),
                                                  onTap: () {
                                                    Navigator.pop(context);
                                                    context.read<MessageProvider>().selectImage();
                                                  },
                                                ),
                                                ListTile(
                                                  leading: const Icon(Icons.insert_drive_file, color: Colors.white),
                                                  title: const Text("Select a File",
                                                      style: TextStyle(color: Colors.white)),
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
                                  child: _showVoiceRecorder
                                      ? VoiceRecorderWidget(
                                          onTranscriptReady: (transcript) {
                                            setState(() {
                                              textController.text = transcript;
                                              _showVoiceRecorder = false;
                                            });
                                          },
                                          onClose: () {
                                            setState(() {
                                              _showVoiceRecorder = false;
                                            });
                                          },
                                        )
                                      : ConstrainedBox(
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
                                            decoration: InputDecoration(
                                              hintText: 'Message',
                                              hintStyle: const TextStyle(fontSize: 14.0, color: Colors.grey),
                                              focusedBorder: InputBorder.none,
                                              enabledBorder: InputBorder.none,
                                              contentPadding: const EdgeInsets.only(top: 8, bottom: 10),
                                            ),
                                            maxLines: null,
                                            keyboardType: TextInputType.multiline,
                                            style:
                                                TextStyle(fontSize: 14.0, color: Colors.grey.shade200, height: 24 / 14),
                                          ),
                                        ),
                                ),
                                if (shouldShowVoiceRecorderButton())
                                  GestureDetector(
                                    child: Container(
                                      padding: const EdgeInsets.only(top: 14, bottom: 14, left: 14, right: 14),
                                      child: const Icon(
                                        Icons.mic_outlined,
                                        color: Color(0xFFF7F4F4),
                                        size: 20.0,
                                      ),
                                    ),
                                    onTap: () {
                                      setState(() {
                                        _showVoiceRecorder = true;
                                      });
                                    },
                                  ),
                                !shouldShowSendButton(provider)
                                    ? const SizedBox.shrink()
                                    : GestureDetector(
                                        onTap: provider.sendingMessage || provider.isUploadingFiles
                                            ? null
                                            : () {
                                                String message = textController.text;
                                                if (message.isEmpty) return;
                                                if (connectivityProvider.isConnected) {
                                                  _sendMessageUtil(message);
                                                } else {
                                                  ScaffoldMessenger.of(context).showSnackBar(
                                                    const SnackBar(
                                                      content:
                                                          Text('Please check your internet connection and try again'),
                                                      duration: Duration(seconds: 2),
                                                    ),
                                                  );
                                                }
                                              },
                                        child: Container(
                                          padding: const EdgeInsets.all(4),
                                          margin: const EdgeInsets.only(top: 10, bottom: 10, right: 6),
                                          decoration: const BoxDecoration(
                                            color: Colors.white,
                                            shape: BoxShape.circle,
                                          ),
                                          child: const Icon(
                                            Icons.arrow_upward_outlined,
                                            color: Colors.black,
                                            size: 20.0,
                                          ),
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

  _sendMessageUtil(String text) {
    var provider = context.read<MessageProvider>();
    MixpanelManager().chatMessageSent(text);
    provider.setSendingMessage(true);
    provider.addMessageLocally(text);
    scrollToBottom();
    textController.clear();
    provider.sendMessageStreamToServer(text);
    provider.clearSelectedFiles();
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
