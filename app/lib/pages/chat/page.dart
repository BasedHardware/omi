import 'dart:io';

import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/chat/select_text_screen.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/pages/chat/widgets/animated_mini_banner.dart';
import 'package:omi/pages/chat/widgets/user_message.dart';
import 'package:omi/pages/chat/widgets/voice_recorder_widget.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/pages/home/widgets/chat_apps_dropdown_widget.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/app_provider.dart';
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
  late FocusNode textFieldFocusNode;

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
    textFieldFocusNode = FocusNode();

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
      var provider = context.read<MessageProvider>();
      if (provider.messages.isEmpty) {
        provider.refreshMessages();
      }
      scrollToBottom();
      // Auto-focus the text field when chat page opens
      Future.delayed(const Duration(milliseconds: 300), () {
        if (mounted && !_showVoiceRecorder) {
          textFieldFocusNode.requestFocus();
        }
      });
    });
    super.initState();
  }

  @override
  void dispose() {
    textController.dispose();
    scrollController.dispose();
    textFieldFocusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);

    return Consumer2<MessageProvider, ConnectivityProvider>(
      builder: (context, provider, connectivityProvider, child) {
        return Scaffold(
          key: scaffoldKey,
          backgroundColor: Theme.of(context).colorScheme.primary,
          appBar: _buildAppBar(context, provider),
          endDrawer: _buildHistoryDrawer(context),
          body: GestureDetector(
            onTap: () {
              // Hide keyboard when tapping outside textfield
              FocusScope.of(context).unfocus();
            },
            child: Stack(
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
                                    child: Text(connectivityProvider.isConnected ? 'No messages yet!\nWhy don\'t you start a conversation?' : 'Please check your internet connection and try again', textAlign: TextAlign.center, style: const TextStyle(color: Colors.white)),
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
                                            ? (Platform.isAndroid ? MediaQuery.sizeOf(context).height * 0.18 : MediaQuery.sizeOf(context).height * 0.16)
                                            : (Platform.isAndroid ? MediaQuery.sizeOf(context).height * 0.21 : MediaQuery.sizeOf(context).height * 0.19)
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
                                              MixpanelManager().track('Chat Message Copied', properties: {'message': message.text});
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
                                              MixpanelManager().track('Chat Message Text Selected', properties: {'message': message.text});
                                              routeToPage(context, SelectTextScreen(message: message));
                                            },
                                            onShare: () {
                                              MixpanelManager().track('Chat Message Shared', properties: {'message': message.text});
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
                                                      MixpanelManager().track('Chat Message Reported', properties: {'message': message.text});
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
                                        padding: EdgeInsets.only(bottom: bottomPadding, left: 18, right: 18, top: topPadding),
                                        child: message.sender == MessageSender.ai
                                            ? AIMessage(
                                                showTypingIndicator: provider.showTypingIndicator && chatIndex == 0,
                                                message: message,
                                                sendMessage: _sendMessageUtil,
                                                displayOptions: provider.messages.length <= 1 && provider.messageSenderApp(message.appId)?.isNotPersona() == true,
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

                  return Column(
                    children: [
                      const Spacer(),
                      // Selected images display above the send bar
                      Consumer<MessageProvider>(builder: (context, provider, child) {
                        if (provider.selectedFiles.isNotEmpty) {
                          return Container(
                            margin: const EdgeInsets.only(left: 16, right: 16, bottom: 8),
                            height: 70,
                            child: ListView.builder(
                              scrollDirection: Axis.horizontal,
                              itemCount: provider.selectedFiles.length,
                              itemBuilder: (ctx, idx) {
                                return Container(
                                  margin: const EdgeInsets.only(right: 8),
                                  width: 60,
                                  height: 60,
                                  decoration: BoxDecoration(
                                    color: Colors.grey[800],
                                    borderRadius: BorderRadius.circular(8),
                                    image: provider.selectedFileTypes[idx] == 'image'
                                        ? DecorationImage(
                                            image: FileImage(provider.selectedFiles[idx]),
                                            fit: BoxFit.cover,
                                          )
                                        : null,
                                  ),
                                  child: Stack(
                                    children: [
                                      // File icon for non-images
                                      if (provider.selectedFileTypes[idx] != 'image')
                                        const Center(
                                          child: Icon(
                                            Icons.insert_drive_file,
                                            color: Colors.white,
                                            size: 24,
                                          ),
                                        ),
                                      // Loading indicator
                                      if (provider.isFileUploading(provider.selectedFiles[idx].path))
                                        Container(
                                          decoration: BoxDecoration(
                                            color: Colors.black.withOpacity(0.5),
                                            borderRadius: BorderRadius.circular(8),
                                          ),
                                          child: const Center(
                                            child: SizedBox(
                                              width: 16,
                                              height: 16,
                                              child: CircularProgressIndicator(
                                                strokeWidth: 2,
                                                valueColor: AlwaysStoppedAnimation<Color>(Colors.white70),
                                              ),
                                            ),
                                          ),
                                        ),
                                      // Close button
                                      Positioned(
                                        top: 2,
                                        right: 2,
                                        child: GestureDetector(
                                          onTap: () {
                                            provider.clearSelectedFile(idx);
                                          },
                                          child: Container(
                                            width: 20,
                                            height: 20,
                                            decoration: BoxDecoration(
                                              color: Colors.black.withOpacity(0.7),
                                              borderRadius: BorderRadius.circular(10),
                                            ),
                                            child: const Icon(
                                              Icons.close,
                                              size: 14,
                                              color: Colors.white,
                                            ),
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                );
                              },
                            ),
                          );
                        } else {
                          return const SizedBox.shrink();
                        }
                      }),
                      // Send bar
                      Padding(
                        padding: EdgeInsets.only(
                          left: 16,
                          right: 16,
                          bottom: widget.isPivotBottom ? 20 : (textFieldFocusNode.hasFocus ? 20 : 40),
                        ),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.end,
                          children: [
                            Expanded(
                              child: Container(
                                height: 44,
                                decoration: BoxDecoration(
                                  color: Colors.white.withOpacity(0.2),
                                  borderRadius: BorderRadius.circular(22),
                                ),
                                child: Container(
                                  height: 44,
                                  padding: const EdgeInsets.symmetric(horizontal: 16),
                                  child: Row(
                                    crossAxisAlignment: CrossAxisAlignment.center,
                                    children: [
                                      if (shouldShowMenuButton())
                                        GestureDetector(
                                          onTap: () {
                                            // Hide keyboard when attach is clicked
                                            FocusScope.of(context).unfocus();
                                            if (provider.selectedFiles.length > 3) {
                                              ScaffoldMessenger.of(context).showSnackBar(
                                                const SnackBar(
                                                  content: Text('You can only upload 4 files at a time'),
                                                  duration: Duration(seconds: 2),
                                                ),
                                              );
                                              return;
                                            }
                                            _showIOSStyleActionSheet(context);
                                          },
                                          child: SizedBox(
                                            height: 44,
                                            width: 32,
                                            child: Icon(
                                              Icons.add,
                                              color: provider.selectedFiles.length > 3 ? Colors.grey : Colors.white70,
                                              size: 20.0,
                                            ),
                                          ),
                                        ),
                                      Expanded(
                                        child: _showVoiceRecorder
                                            ? VoiceRecorderWidget(
                                                onTranscriptReady: (transcript) {
                                                  setState(() {
                                                    textController.text = transcript;
                                                    _showVoiceRecorder = false;
                                                    context.read<MessageProvider>().setNextMessageOriginIsVoice(true);
                                                  });
                                                },
                                                onClose: () {
                                                  setState(() {
                                                    _showVoiceRecorder = false;
                                                  });
                                                },
                                              )
                                            : Container(
                                                height: 44,
                                                alignment: Alignment.centerLeft,
                                                child: TextField(
                                                  enabled: true,
                                                  controller: textController,
                                                  focusNode: textFieldFocusNode,
                                                  obscureText: false,
                                                  textAlign: TextAlign.start,
                                                  textAlignVertical: TextAlignVertical.center,
                                                  decoration: const InputDecoration(
                                                    hintText: 'Message',
                                                    hintStyle: TextStyle(fontSize: 14.0, color: Colors.white54),
                                                    focusedBorder: InputBorder.none,
                                                    enabledBorder: InputBorder.none,
                                                    contentPadding: EdgeInsets.symmetric(horizontal: 8, vertical: 0),
                                                    isDense: true,
                                                  ),
                                                  maxLines: 1,
                                                  keyboardType: TextInputType.text,
                                                  style: const TextStyle(fontSize: 14.0, color: Colors.white, height: 1.0),
                                                ),
                                              ),
                                      ),
                                      if (shouldShowVoiceRecorderButton())
                                        GestureDetector(
                                          child: SizedBox(
                                            height: 44,
                                            width: 32,
                                            child: Icon(
                                              Icons.mic_outlined,
                                              color: Colors.white70,
                                              size: 20.0,
                                            ),
                                          ),
                                          onTap: () {
                                            // Hide keyboard when mic is clicked
                                            FocusScope.of(context).unfocus();
                                            setState(() {
                                              _showVoiceRecorder = true;
                                            });
                                          },
                                        ),
                                    ],
                                  ),
                                ),
                              ),
                            ),
                            const SizedBox(width: 8),
                            !shouldShowSendButton(provider)
                                ? const SizedBox.shrink()
                                : GestureDetector(
                                    onTap: provider.sendingMessage || provider.isUploadingFiles
                                        ? null
                                        : () {
                                            HapticFeedback.lightImpact(); // Add haptic feedback
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
                                    child: Container(
                                      height: 44, // Same height as textbox
                                      width: 44,
                                      decoration: BoxDecoration(
                                        gradient: const LinearGradient(
                                          colors: [
                                            Color(0xFF6366F1), // Indigo
                                            Color(0xFF8B5CF6), // Purple
                                          ],
                                          begin: Alignment.topLeft,
                                          end: Alignment.bottomRight,
                                        ),
                                        borderRadius: BorderRadius.circular(22),
                                        boxShadow: [
                                          BoxShadow(
                                            color: const Color(0xFF6366F1).withOpacity(0.3),
                                            blurRadius: 8,
                                            offset: const Offset(0, 2),
                                          ),
                                        ],
                                      ),
                                      child: const Icon(
                                        Icons.arrow_upward_rounded,
                                        color: Colors.white,
                                        size: 20.0,
                                      ),
                                    ),
                                  ),
                          ],
                        ),
                      ),
                    ],
                  );
                }),
              ],
            ),
          ),
        );
      },
    );
  }

  _sendMessageUtil(String text) {
    var provider = context.read<MessageProvider>();
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

  PreferredSizeWidget _buildAppBar(BuildContext context, MessageProvider provider) {
    return AppBar(
      backgroundColor: Theme.of(context).colorScheme.surface,
      elevation: 0,
      leading: IconButton(
        icon: const Icon(Icons.arrow_back, color: Colors.white),
        onPressed: () => Navigator.of(context).pop(),
      ),
      title: Consumer<AppProvider>(
        builder: (context, appProvider, child) {
          return _buildAppSelection(context, appProvider);
        },
      ),
      centerTitle: true,
      actions: [
        IconButton(
          icon: const Icon(Icons.history, color: Colors.white),
          onPressed: () {
            scaffoldKey.currentState?.openEndDrawer();
          },
        ),
      ],
      bottom: provider.isLoadingMessages
          ? PreferredSize(
              preferredSize: const Size.fromHeight(10),
              child: Container(
                width: double.infinity,
                height: 10,
                color: Colors.green,
                child: const Center(
                  child: Text(
                    'Syncing messages with server...',
                    style: TextStyle(color: Colors.white, fontSize: 12),
                  ),
                ),
              ),
            )
          : null,
    );
  }

  Widget _buildAppSelection(BuildContext context, AppProvider provider) {
    var selectedApp = provider.apps.firstWhereOrNull((app) => app.id == provider.selectedChatAppId);

    return PopupMenuButton<String>(
      iconSize: 164,
      icon: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        mainAxisAlignment: MainAxisAlignment.center,
        mainAxisSize: MainAxisSize.max,
        children: [
          selectedApp != null ? _getAppAvatar(selectedApp) : _getOmiAvatar(),
          const SizedBox(width: 8),
          Container(
            constraints: const BoxConstraints(
              maxWidth: 100,
            ),
            child: Text(
              selectedApp != null ? selectedApp.getName() : "Omi",
              style: const TextStyle(color: Colors.white, fontSize: 16),
              overflow: TextOverflow.fade,
            ),
          ),
          const SizedBox(width: 8),
          const SizedBox(
            width: 24,
            child: Icon(Icons.keyboard_arrow_down, color: Colors.white60, size: 16),
          ),
        ],
      ),
      constraints: const BoxConstraints(
        minWidth: 250.0,
        maxWidth: 250.0,
        maxHeight: 350.0,
      ),
      offset: Offset((MediaQuery.sizeOf(context).width - 250) / 2 / MediaQuery.devicePixelRatioOf(context), 50),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(16))),
      onSelected: (String? val) async {
        if (val == null || val == provider.selectedChatAppId) {
          return;
        }

        // clear chat
        if (val == 'clear_chat') {
          showDialog(
            context: context,
            builder: (ctx) {
              return getDialog(context, () {
                Navigator.of(context).pop();
              }, () {
                context.read<MessageProvider>().clearChat();
                Navigator.of(context).pop();
              }, "Clear Chat?", "Are you sure you want to clear the chat? This action cannot be undone.");
            },
          );
          return;
        }

        // enable apps - navigate back to home and show apps page
        if (val == 'enable') {
          MixpanelManager().pageOpened('Chat Apps');
          Navigator.of(context).pushReplacement(
            MaterialPageRoute(
              builder: (context) => const HomePageWrapper(navigateToRoute: '/apps'),
            ),
          );
          return;
        }

        // select app by id
        provider.setSelectedChatAppId(val);
        await context.read<MessageProvider>().refreshMessages(dropdownSelected: true);
        var app = provider.getSelectedApp();
        if (context.read<MessageProvider>().messages.isEmpty) {
          context.read<MessageProvider>().sendInitialAppMessage(app);
        }
      },
      itemBuilder: (BuildContext context) {
        return _getAppsDropdownItems(context, provider);
      },
      color: Colors.grey.shade900,
    );
  }

  Widget _getAppAvatar(App app) {
    return CachedNetworkImage(
      imageUrl: app.getImageUrl(),
      imageBuilder: (context, imageProvider) {
        return CircleAvatar(
          backgroundColor: Colors.white,
          radius: 12,
          backgroundImage: imageProvider,
        );
      },
      errorWidget: (context, url, error) {
        return const CircleAvatar(
          backgroundColor: Colors.white,
          radius: 12,
          child: Icon(Icons.error_outline_rounded),
        );
      },
      progressIndicatorBuilder: (context, url, progress) => CircleAvatar(
        backgroundColor: Colors.white,
        radius: 12,
        child: CircularProgressIndicator(
          value: progress.progress,
          valueColor: const AlwaysStoppedAnimation<Color>(Colors.white),
        ),
      ),
    );
  }

  Widget _getOmiAvatar() {
    return Container(
      decoration: BoxDecoration(
        image: DecorationImage(
          image: AssetImage(Assets.images.background.path),
          fit: BoxFit.cover,
        ),
        borderRadius: const BorderRadius.all(Radius.circular(16.0)),
      ),
      height: 24,
      width: 24,
      child: Stack(
        alignment: Alignment.center,
        children: [
          Image.asset(
            Assets.images.herologo.path,
            height: 16,
            width: 16,
          ),
        ],
      ),
    );
  }

  List<PopupMenuItem<String>> _getAppsDropdownItems(BuildContext context, AppProvider provider) {
    var selectedApp = provider.apps.firstWhereOrNull((app) => app.id == provider.selectedChatAppId);
    return [
      const PopupMenuItem<String>(
        height: 40,
        value: 'clear_chat',
        child: Padding(
          padding: EdgeInsets.only(left: 32),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text('Clear Chat', style: TextStyle(color: Colors.redAccent, fontSize: 16)),
              SizedBox(
                width: 24,
                child: Icon(Icons.delete, color: Colors.redAccent, size: 16),
              ),
            ],
          ),
        ),
      ),
      const PopupMenuItem<String>(
        height: 1,
        child: Divider(height: 1),
      ),
      const PopupMenuItem<String>(
        value: 'enable',
        height: 40,
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          mainAxisAlignment: MainAxisAlignment.start,
          mainAxisSize: MainAxisSize.max,
          children: [
            SizedBox(
              width: 24,
              child: Icon(Icons.arrow_forward_ios, color: Colors.white, size: 16),
            ),
            SizedBox(width: 8),
            Expanded(
              child: Row(
                mainAxisSize: MainAxisSize.max,
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text('Enable Apps', style: TextStyle(color: Colors.white, fontSize: 16)),
                  SizedBox(
                    width: 24,
                    child: Icon(Icons.apps, color: Colors.white60, size: 16),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
      const PopupMenuItem<String>(
        height: 1,
        child: Divider(height: 1),
      ),
      PopupMenuItem<String>(
        height: 40,
        value: 'no_selected',
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            _getOmiAvatar(),
            const SizedBox(width: 10),
            Expanded(
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    "Omi",
                    style: TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                  ),
                  selectedApp == null
                      ? const SizedBox(
                          width: 24,
                          child: Icon(Icons.check, color: Colors.white60, size: 16),
                        )
                      : const SizedBox.shrink(),
                ],
              ),
            ),
          ],
        ),
      ),
      ...provider.apps.where((app) => app.worksWithChat() && app.enabled).map((app) {
        return PopupMenuItem<String>(
          height: 40,
          value: app.id,
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            mainAxisAlignment: MainAxisAlignment.start,
            children: [
              _getAppAvatar(app),
              const SizedBox(width: 8),
              Expanded(
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Text(
                        overflow: TextOverflow.fade,
                        app.getName(),
                        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500, fontSize: 16),
                      ),
                    ),
                    selectedApp?.id == app.id
                        ? const SizedBox(
                            width: 24,
                            child: Icon(Icons.check, color: Colors.white60, size: 16),
                          )
                        : const SizedBox.shrink(),
                  ],
                ),
              ),
            ],
          ),
        );
      }).toList(),
    ];
  }

  void _showIOSStyleActionSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (BuildContext context) {
        return Container(
          margin: const EdgeInsets.all(10),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              // Main options container
              Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF1C1C1E).withOpacity(0.95),
                  borderRadius: BorderRadius.circular(13),
                ),
                child: Column(
                  children: [
                    _buildIOSActionItem(
                      title: "Take Photo",
                      icon: Icons.camera_alt,
                      onTap: () {
                        HapticFeedback.selectionClick();
                        Navigator.pop(context);
                        context.read<MessageProvider>().captureImage();
                      },
                      isFirst: true,
                    ),
                    _buildDivider(),
                    _buildIOSActionItem(
                      title: "Photo Library",
                      icon: Icons.photo_library,
                      onTap: () {
                        HapticFeedback.selectionClick();
                        Navigator.pop(context);
                        context.read<MessageProvider>().selectImage();
                      },
                    ),
                    _buildDivider(),
                    _buildIOSActionItem(
                      title: "Choose File",
                      icon: Icons.folder,
                      onTap: () {
                        HapticFeedback.selectionClick();
                        Navigator.pop(context);
                        context.read<MessageProvider>().selectFile();
                      },
                      isLast: true,
                    ),
                  ],
                ),
              ),
              SizedBox(height: MediaQuery.of(context).padding.bottom + 10),
            ],
          ),
        );
      },
    );
  }

  Widget _buildIOSActionItem({
    required String title,
    required VoidCallback onTap,
    IconData? icon,
    bool isFirst = false,
    bool isLast = false,
    bool isCancel = false,
  }) {
    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.vertical(
          top: isFirst ? const Radius.circular(13) : Radius.zero,
          bottom: isLast ? const Radius.circular(13) : Radius.zero,
        ),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.symmetric(vertical: 16, horizontal: 20),
          child: Row(
            children: [
              Expanded(
                child: Text(
                  title,
                  style: TextStyle(
                    color: isCancel ? Colors.red : Colors.blue,
                    fontSize: 20,
                    fontWeight: isCancel ? FontWeight.w600 : FontWeight.w400,
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
              if (icon != null && !isCancel)
                Icon(
                  icon,
                  color: Colors.grey.shade600,
                  size: 24,
                ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildDivider() {
    return Container(
      height: 0.5,
      color: Colors.grey.shade700,
      margin: const EdgeInsets.symmetric(horizontal: 20),
    );
  }

  Widget _buildHistoryDrawer(BuildContext context) {
    return SizedBox(
      width: MediaQuery.of(context).size.width * 0.6,
      child: Drawer(
        backgroundColor: Theme.of(context).colorScheme.primary,
        child: Column(
          children: [
            // Header
            Container(
              padding: EdgeInsets.only(
                top: MediaQuery.of(context).padding.top + 20,
                left: 20,
                right: 20,
                bottom: 20,
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text(
                    'History',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 24,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, color: Colors.white),
                    onPressed: () {
                      Navigator.of(context).pop();
                    },
                  ),
                ],
              ),
            ),
            const Divider(color: Colors.white24),
            // Content
            Expanded(
              child: Padding(
                padding: const EdgeInsets.all(20),
                child: Column(
                  children: [
                    // Placeholder content - replace with actual history implementation
                    Container(
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: Colors.white.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Center(
                        child: Text(
                          'History feature\ncoming soon!',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            color: Colors.white70,
                            fontSize: 16,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
