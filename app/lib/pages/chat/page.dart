import 'dart:async';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:collection/collection.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/gen/fonts.gen.dart';
import 'package:omi/pages/chat/select_text_screen.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/pages/chat/widgets/suggestion_chips.dart';
import 'package:omi/pages/chat/widgets/user_message.dart';
import 'package:omi/pages/chat/widgets/voice_recorder_widget.dart';
import 'package:omi/pages/home/page.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/providers/chat_session_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/pages/chat/widgets/welcome_screen.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

import 'widgets/message_action_menu.dart';
import 'widgets/top_notification_banner.dart';

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
  bool _isInitialLoad = true;

  // Notification banner state
  bool _showNotificationBanner = false;
  String _notificationMessage = '';
  NotificationType _notificationType = NotificationType.success;

  // Chat swipe state
  String? _swipingChatId;
  double _swipeProgress = 0.0; // Track swipe progress for smooth animation

  // Drawer state for dimming effect
  bool _isDrawerOpen = false;

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
    textController.addListener(() {
      setState(() {});
    });

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

      // Load all sessions across all apps on initialization
      await context.read<ChatSessionProvider>().loadSessions();

      scrollToBottom();
      // Removed auto-focus to prevent keyboard from always appearing
      // User must explicitly tap the chat input to show keyboard
    });

    // Monitor drawer state for dimming effect
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _startDrawerStateMonitoring();
    });

    super.initState();
  }

  void _startDrawerStateMonitoring() {
    // Check drawer state periodically for smooth transitions
    Timer.periodic(const Duration(milliseconds: 50), (timer) {
      if (!mounted) {
        timer.cancel();
        return;
      }

      final isCurrentlyOpen = scaffoldKey.currentState?.isEndDrawerOpen ?? false;
      if (isCurrentlyOpen != _isDrawerOpen) {
        setState(() {
          _isDrawerOpen = isCurrentlyOpen;
        });

        // Subtle vibration when drawer opens or closes
        if (isCurrentlyOpen) {
          HapticFeedback.lightImpact(); // Opening feedback
        } else {
          HapticFeedback.lightImpact(); // Closing feedback
        }
      }
    });
  }

  @override
  void dispose() {
    textController.dispose();
    scrollController.dispose();
    textFieldFocusNode.dispose();
    super.dispose();
  }

  // Notification banner management methods
  void _showNotification(String message, {NotificationType type = NotificationType.success}) {
    setState(() {
      _notificationMessage = message;
      _notificationType = type;
      _showNotificationBanner = true;
    });
  }

  void _hideNotification() {
    setState(() {
      _showNotificationBanner = false;
    });
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
          endDrawer: _buildSessionsDrawer(context),
          resizeToAvoidBottomInset: true,
          body: Stack(
            children: [
              Positioned.fill(
                child: GestureDetector(
                  onTap: () {
                    // Hide keyboard when tapping outside textfield
                    FocusScope.of(context).unfocus();
                  },
                  child: Column(
                    children: [
                      // Notification banner (appears below AppBar, above messages)
                      TopNotificationBanner(
                        message: _notificationMessage,
                        isVisible: _showNotificationBanner,
                        type: _notificationType,
                        onDismiss: _hideNotification,
                      ),
                      // Messages area - takes up remaining space
                      Expanded(
                        child: provider.isLoadingMessages && !provider.hasCachedMessages
                            ? Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
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
                                    mainAxisAlignment: MainAxisAlignment.center,
                                    children: [
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
                                : provider.messages.isEmpty
                                    ? (connectivityProvider.isConnected
                                        ? WelcomeScreen(
                                            sendMessage: _sendMessageUtil,
                                            appName: context.read<AppProvider>().getSelectedApp()?.name,
                                          )
                                        : Center(
                                            child: Padding(
                                              padding: const EdgeInsets.only(bottom: 32.0),
                                              child: Text('Please check your internet connection and try again',
                                                  textAlign: TextAlign.center,
                                                  style: const TextStyle(color: Colors.white)),
                                            ),
                                          ))
                                    : ListView.builder(
                                        shrinkWrap: false,
                                        reverse: true,
                                        controller: scrollController,
                                        padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 16),
                                        itemCount: provider.messages.length,
                                        itemBuilder: (context, chatIndex) {
                                          final message = provider.messages[chatIndex];
                                          double topPadding = chatIndex == provider.messages.length - 1 ? 8 : 16;

                                          double bottomPadding = chatIndex == 0 ? 16 : 0;
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
                                                    MixpanelManager().track('Chat Message Copied',
                                                        properties: {'message': message.text});
                                                    await Clipboard.setData(
                                                        ClipboardData(text: message.text.decodeString));
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
                                                    MixpanelManager().track('Chat Message Shared',
                                                        properties: {'message': message.text});
                                                    Share.share(
                                                      '${message.text.decodeString}\n\nResponse from Omi. Get yours at https://omi.me',
                                                      subject: 'Chat with Omi',
                                                    );
                                                    Navigator.pop(context);
                                                  },
                                                  onThumbsUp: message.sender == MessageSender.ai && message.askForNps
                                                      ? () {
                                                          provider.setMessageNps(message, 1);
                                                          Navigator.pop(context);
                                                          AppSnackbar.showSnackbar('Thank you for your feedback!');
                                                        }
                                                      : null,
                                                  onThumbsDown: message.sender == MessageSender.ai && message.askForNps
                                                      ? () {
                                                          provider.setMessageNps(message, 0);
                                                          Navigator.pop(context);
                                                          AppSnackbar.showSnackbar('Thank you for your feedback!');
                                                        }
                                                      : null,
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
                                                            context
                                                                .read<MessageProvider>()
                                                                .removeLocalMessage(message.id);
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
                                              padding: EdgeInsets.only(bottom: bottomPadding, top: topPadding),
                                              child: message.sender == MessageSender.ai
                                                  ? AIMessage(
                                                      showTypingIndicator:
                                                          provider.showTypingIndicator && chatIndex == 0,
                                                      message: message,
                                                      sendMessage: _sendMessageUtil,
                                                      displayOptions: provider.messages.length <= 1 &&
                                                          provider.messageSenderApp(message.appId)?.isNotPersona() ==
                                                              true,
                                                      appSender: provider.messageSenderApp(message.appId),
                                                      updateConversation: (ServerConversation conversation) {
                                                        context
                                                            .read<ConversationProvider>()
                                                            .updateConversation(conversation);
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
                      // Suggestion chips - only show when chat is empty
                      if (provider.messages.isEmpty && connectivityProvider.isConnected)
                        SuggestionChips(sendMessage: _sendMessageUtil),
                      // Send message area - fixed at bottom
                      Container(
                        margin: const EdgeInsets.only(top: 10),
                        decoration: const BoxDecoration(
                          color: Color(0xFF1f1f25),
                          borderRadius: BorderRadius.only(
                            topLeft: Radius.circular(22),
                            topRight: Radius.circular(22),
                          ),
                        ),
                        child: Consumer<HomeProvider>(builder: (context, home, child) {
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
                              // Selected images display above the send bar
                              Consumer<MessageProvider>(builder: (context, provider, child) {
                                if (provider.selectedFiles.isNotEmpty) {
                                  return Container(
                                    margin: const EdgeInsets.only(top: 16, bottom: 8),
                                    padding: const EdgeInsets.symmetric(horizontal: 16),
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
                                            borderRadius: BorderRadius.circular(16),
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
                                                    borderRadius: BorderRadius.circular(16),
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
                                                top: 4,
                                                right: 4,
                                                child: GestureDetector(
                                                  onTap: () {
                                                    provider.clearSelectedFile(idx);
                                                  },
                                                  child: Container(
                                                    width: 16,
                                                    height: 16,
                                                    decoration: BoxDecoration(
                                                      color: Colors.white,
                                                      borderRadius: BorderRadius.circular(10),
                                                    ),
                                                    child: const Icon(
                                                      FontAwesomeIcons.xmark,
                                                      size: 10,
                                                      color: Colors.black,
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
                                  left: 0,
                                  right: 16,
                                  top: provider.selectedFiles.isNotEmpty ? 0 : 16,
                                  bottom: widget.isPivotBottom ? 20 : (textFieldFocusNode.hasFocus ? 20 : 40),
                                ),
                                child: Row(
                                  crossAxisAlignment: CrossAxisAlignment.end,
                                  children: [
                                    Expanded(
                                      child: Container(
                                        padding: const EdgeInsets.only(left: 16, right: 8),
                                        child: Row(
                                          crossAxisAlignment: CrossAxisAlignment.end,
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
                                                child: Container(
                                                  margin: const EdgeInsets.only(right: 4),
                                                  height: 44,
                                                  width: 44,
                                                  alignment: Alignment.center,
                                                  child: FaIcon(
                                                    FontAwesomeIcons.plus,
                                                    color:
                                                        provider.selectedFiles.length > 3 ? Colors.grey : Colors.white,
                                                    size: 20,
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
                                                          context
                                                              .read<MessageProvider>()
                                                              .setNextMessageOriginIsVoice(true);
                                                        });
                                                      },
                                                      onClose: () {
                                                        setState(() {
                                                          _showVoiceRecorder = false;
                                                        });
                                                      },
                                                    )
                                                  : Container(
                                                      alignment: Alignment.centerLeft,
                                                      child: TextField(
                                                        enabled: true,
                                                        controller: textController,
                                                        focusNode: textFieldFocusNode,
                                                        obscureText: false,
                                                        textAlign: TextAlign.start,
                                                        textAlignVertical: TextAlignVertical.center,
                                                        decoration: const InputDecoration(
                                                          hintText: 'Ask Anything',
                                                          hintStyle: TextStyle(fontSize: 16.0, color: Colors.white54),
                                                          focusedBorder: InputBorder.none,
                                                          enabledBorder: InputBorder.none,
                                                          contentPadding:
                                                              EdgeInsets.symmetric(horizontal: 8, vertical: 12),
                                                          isDense: true,
                                                        ),
                                                        minLines: 1,
                                                        maxLines: 10,
                                                        keyboardType: TextInputType.multiline,
                                                        textCapitalization: TextCapitalization.sentences,
                                                        style: const TextStyle(
                                                            fontSize: 16.0, color: Colors.white, height: 1.4),
                                                      ),
                                                    ),
                                            ),
                                            if (shouldShowVoiceRecorderButton())
                                              textController.text.isNotEmpty
                                                  ? GestureDetector(
                                                      onTap: () {
                                                        textController.clear();
                                                      },
                                                      child: Container(
                                                        height: 44,
                                                        width: 44,
                                                        alignment: Alignment.center,
                                                        child: const FaIcon(
                                                          FontAwesomeIcons.xmark,
                                                          color: Colors.white,
                                                          size: 20,
                                                        ),
                                                      ),
                                                    )
                                                  : GestureDetector(
                                                      child: Container(
                                                        height: 44,
                                                        width: 44,
                                                        alignment: Alignment.center,
                                                        child: const FaIcon(
                                                          FontAwesomeIcons.microphone,
                                                          color: Colors.white,
                                                          size: 20,
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
                                    // const SizedBox(width: 8),
                                    !shouldShowSendButton(provider)
                                        ? const SizedBox.shrink()
                                        : ValueListenableBuilder<TextEditingValue>(
                                            valueListenable: textController,
                                            builder: (context, value, child) {
                                              bool canSend = value.text.trim().isNotEmpty &&
                                                  !provider.sendingMessage &&
                                                  !provider.isUploadingFiles &&
                                                  connectivityProvider.isConnected;

                                              return GestureDetector(
                                                onTap: canSend
                                                    ? () {
                                                        HapticFeedback.mediumImpact();
                                                        String message = textController.text.trim();
                                                        if (message.isEmpty) return;
                                                        _sendMessageUtil(message);
                                                      }
                                                    : null,
                                                child: Container(
                                                  height: 44,
                                                  width: 44,
                                                  decoration: BoxDecoration(
                                                    color: canSend ? Colors.white : Colors.grey.withOpacity(0.3),
                                                    borderRadius: BorderRadius.circular(22),
                                                    boxShadow: canSend
                                                        ? [
                                                            BoxShadow(
                                                              color: Colors.black.withOpacity(0.1),
                                                              blurRadius: 8,
                                                              offset: const Offset(0, 2),
                                                            ),
                                                          ]
                                                        : [],
                                                  ),
                                                  child: Icon(
                                                    FontAwesomeIcons.arrowUp,
                                                    color: canSend ? const Color(0xFF35343B) : Colors.grey,
                                                    size: 20,
                                                  ),
                                                ),
                                              );
                                            },
                                          ),
                                  ],
                                ),
                              ),
                            ],
                          );
                        }),
                      ), // Close builder widget
                    ], // Close Column children
                  ), // Close Column
                ), // Close GestureDetector
              ), // Close Positioned.fill
              // Dimming overlay positioned to cover body and extend up to AppBar
              Positioned(
                top: -kToolbarHeight - MediaQuery.of(context).padding.top, // Extend upward to cover AppBar
                left: 0,
                right: 0,
                bottom: 0,
                child: IgnorePointer(
                  ignoring: !_isDrawerOpen, // Only intercept touches when drawer is open
                  child: AnimatedOpacity(
                    opacity: _isDrawerOpen ? 0.75 : 0.0, // Enhanced dimming (75%) for strong focus separation
                    duration: const Duration(milliseconds: 300), // Smooth transition
                    child: Container(
                      color: const Color(0xFF1A1A1A), // Dark greyish color for more natural dimming
                      child: GestureDetector(
                        onTap: () {
                          // Close drawer when tapping on dimmed area
                          if (_isDrawerOpen) {
                            Navigator.of(context).pop();
                          }
                        },
                      ),
                    ),
                  ),
                ),
              ),
            ], // Close body Stack children
          ), // Close body Stack
        ); // Close Scaffold
      },
    );
  }

  _sendMessageUtil(String text) {
    // Remove focus from text field
    textFieldFocusNode.unfocus();

    var provider = context.read<MessageProvider>();
    provider.setSendingMessage(true);
    provider.addMessageLocally(text);
    textController.clear();

    // Scroll to align user's message to top of screen
    Future.delayed(const Duration(milliseconds: 100), () {
      scrollToBottom();
    });

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

  void _handleAppSelection(String? val, AppProvider provider) {
    if (val == null || val == provider.selectedChatAppId) {
      return;
    }

    // Unfocus the text field to prevent keyboard issues
    textFieldFocusNode.unfocus();

    // clear chat
    if (val == 'clear_chat') {
      _showClearChatDialog();
      return;
    }

    // enable apps - navigate back to home and show apps page
    if (val == 'enable') {
      _navigateToAppsPage();
      return;
    }

    // select app by id
    _selectApp(val, provider);
  }

  void _showClearChatDialog() {
    if (!mounted) return;

    showDialog(
      context: context,
      builder: (ctx) {
        return getDialog(context, () {
          Navigator.of(context).pop();
        }, () {
          if (mounted) {
            context.read<MessageProvider>().clearChat();
            Navigator.of(context).pop();
          }
        }, "Clear Chat?", "Are you sure you want to clear the chat? This action cannot be undone.");
      },
    );
  }

  void _navigateToAppsPage() {
    if (!mounted) return;

    MixpanelManager().pageOpened('Chat Apps');
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (context) => const HomePageWrapper(navigateToRoute: '/apps'),
      ),
    );
  }

  void _selectApp(String appId, AppProvider appProvider) async {
    if (!mounted) return;

    // Mark that we're no longer on initial load to prevent auto-focus
    _isInitialLoad = false;

    // Store references before async operation
    final messageProvider = mounted ? context.read<MessageProvider>() : null;
    if (messageProvider == null) return;

    // Set the selected app
    appProvider.setSelectedChatAppId(appId);

    // Clear any selected chats to show welcome screen
    final chatSessionProvider = mounted ? context.read<ChatSessionProvider>() : null;
    if (chatSessionProvider != null) {
      await chatSessionProvider.switchToApp(appId);
    }

    // Add a small delay to let the keyboard animation complete
    // This prevents the widget from being unmounted during the keyboard transition
    await Future.delayed(const Duration(milliseconds: 100));

    // Check if widget is still mounted after delay
    if (!mounted) return;

    // Load sessions for the new app
    if (chatSessionProvider != null) {
      await chatSessionProvider.loadSessions();
    }

    // Perform async operation
    await messageProvider.refreshMessages(dropdownSelected: true);

    // Check if widget is still mounted before proceeding
    if (!mounted) return;
  }

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
        Container(
          width: 36,
          height: 36,
          margin: const EdgeInsets.only(right: 12),
          decoration: const BoxDecoration(
            color: Color(0xFF1F1F25),
            shape: BoxShape.circle,
          ),
          child: IconButton(
            padding: EdgeInsets.zero,
            icon: const Icon(FontAwesomeIcons.clockRotateLeft, color: Colors.white70, size: 16),
            tooltip: 'Chats',
            onPressed: () {
              HapticFeedback.lightImpact(); // Subtle vibration like streaming responses
              FocusScope.of(context).unfocus();
              // Open drawer immediately for better UX, then load sessions
              scaffoldKey.currentState?.openEndDrawer();
              // Load sessions in background without blocking UI
              context.read<ChatSessionProvider>().loadSessions(refresh: true);
            },
          ),
        ),
      ],
      bottom: provider.isLoadingMessages
          ? PreferredSize(
              preferredSize: const Size.fromHeight(32),
              child: Container(
                width: double.infinity,
                height: 32,
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

  Widget _buildSearchBar(ChatSessionProvider sessions) {
    return Container(
      height: 40, // Match pencil icon exact height
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.08),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Colors.white.withOpacity(0.12), width: 1),
      ),
      child: TextField(
        style: const TextStyle(color: Colors.white, fontSize: 14),
        decoration: const InputDecoration(
          hintText: 'Search',
          hintStyle: TextStyle(color: Colors.white60, fontSize: 14),
          prefixIcon: Icon(Icons.search_rounded, color: Colors.white70, size: 20),
          border: InputBorder.none,
          contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 13),
        ),
        textAlign: TextAlign.left,
        textAlignVertical: TextAlignVertical.center,
        onChanged: (query) => sessions.updateSearchQuery(query),
      ),
    );
  }

  Widget _buildSessionsDrawer(BuildContext context) {
    return Drawer(
      backgroundColor: Colors.black, // Pure black background
      child: SafeArea(
        child: Consumer3<AppProvider, ChatSessionProvider, MessageProvider>(
          builder: (context, appProvider, sessions, messageProvider, _) {
            final appId = appProvider.selectedChatAppId;
            // AppProvider provides clean state - no conversion needed
            final effectiveAppId = appId;

            final selectedId = sessions.selectedSessionId;

            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header section with search and pencil icon
                Container(
                  padding: const EdgeInsets.all(16),
                  child: Row(
                    children: [
                      // Search bar (takes most space)
                      Expanded(child: _buildSearchBar(sessions)),
                      const SizedBox(width: 8),
                      // New chat button
                      Container(
                        decoration: BoxDecoration(
                          color: Colors.white.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child: IconButton(
                          visualDensity: VisualDensity.compact,
                          padding: const EdgeInsets.all(8),
                          icon: const Icon(Icons.border_color, color: Colors.white, size: 16),
                          onPressed: () async {
                            final created = await sessions.createSession(appId: effectiveAppId);
                            if (created != null) {
                              _showNotification('New chat created');
                              await messageProvider.refreshMessages(dropdownSelected: true);
                              if (mounted) Navigator.of(context).maybePop();
                            }
                          },
                          tooltip: 'New Chat',
                        ),
                      ),
                    ],
                  ),
                ),
                const Divider(height: 1, color: Colors.white12),
                if (sessions.isLoading)
                  const Expanded(
                    child: Center(
                        child: CircularProgressIndicator(valueColor: AlwaysStoppedAnimation<Color>(Colors.white))),
                  )
                else if (sessions.filteredSessions.isEmpty && sessions.searchQuery.isNotEmpty)
                  const Expanded(
                    child: Center(
                      child: Text('No chats found', style: TextStyle(color: Colors.white60)),
                    ),
                  )
                else if (sessions.sessions.isEmpty)
                  const Expanded(
                    child: Center(
                      child: Text('No chats yet', style: TextStyle(color: Colors.white60)),
                    ),
                  )
                else
                  Expanded(
                    child: ListView.builder(
                      itemCount: sessions.filteredSessions.length,
                      itemExtent: 52, // Explicit item height prevents infinite size issues
                      physics: const BouncingScrollPhysics(), // Better scroll physics
                      padding: const EdgeInsets.symmetric(
                          horizontal: 0, vertical: 8), // Remove horizontal padding for full width
                      itemBuilder: (ctx, idx) {
                        final s = sessions.filteredSessions[idx];
                        // Smooth color calculation for gradual transitions
                        final isSelected = s.id == selectedId;
                        final isBeingSwiped = s.id == _swipingChatId;

                        // Calculate smooth color with gradual opacity
                        final Color cardColor;
                        if (isSelected) {
                          cardColor = const Color(0xFF2A2A2A); // Full highlight for selected
                        } else if (isBeingSwiped) {
                          cardColor =
                              Color.fromRGBO(42, 42, 42, _swipeProgress * 0.8); // Gradual highlight during swipe
                        } else {
                          cardColor = Colors.transparent; // No highlight
                        }
                        final appName = _getAppNameById(s.appId);
                        return SizedBox(
                          height: 52, // Fixed height for entire list item (48px content + 4px spacing)
                          child: Padding(
                            padding: const EdgeInsets.only(bottom: 2), // Bottom spacing for card separation
                            child: Padding(
                              padding: const EdgeInsets.symmetric(horizontal: 8), // Card boundary padding
                              child: ClipRRect(
                                // Clip with rounded corners to match card design
                                borderRadius: BorderRadius.circular(16),
                                child: Dismissible(
                                  key: Key(s.id),
                                  direction: DismissDirection.endToStart,
                                  dismissThresholds: const {
                                    DismissDirection.endToStart: 0.3
                                  }, // Lower threshold for easier access
                                  movementDuration: const Duration(milliseconds: 150), // Snappy animation
                                  confirmDismiss: (direction) async {
                                    // Subtle vibration for delete action
                                    HapticFeedback.lightImpact();

                                    // Clear swipe state immediately
                                    setState(() {
                                      _swipingChatId = null;
                                      _swipeProgress = 0.0;
                                    });

                                    // Delete session and return result to control dismissal
                                    final ok = await sessions.deleteSession(sessionId: s.id);
                                    if (ok) {
                                      _showNotification('Chat deleted');
                                      return true; // Allow dismissal
                                    } else {
                                      _showNotification('Failed to delete chat', type: NotificationType.error);
                                      return false; // Prevent dismissal and restore item
                                    }
                                  },
                                  onUpdate: (details) {
                                    // Track swipe progress for smooth visual feedback
                                    setState(() {
                                      if (details.progress > 0.05) {
                                        // Start tracking at 5% swipe
                                        _swipingChatId = s.id;
                                        _swipeProgress =
                                            (details.progress * 2).clamp(0.0, 1.0); // Gradual opacity from 0 to 1
                                      } else {
                                        _swipingChatId = null;
                                        _swipeProgress = 0.0;
                                      }
                                    });
                                  },
                                  background: Container(
                                    width: double.infinity,
                                    height: 50, // Match available space (52px parent - 2px spacing)
                                    padding: const EdgeInsets.symmetric(
                                        horizontal: 16, vertical: 12), // Identical padding to main card
                                    decoration: const BoxDecoration(
                                      color: Colors.red,
                                      borderRadius: BorderRadius.only(
                                        topRight: Radius.circular(16), // Rounded on right side only
                                        bottomRight: Radius.circular(16), // Rounded on right side only
                                        topLeft: Radius.zero, // Straight left edge to merge with greyish card
                                        bottomLeft: Radius.zero, // Straight left edge to merge with greyish card
                                      ),
                                    ),
                                    alignment: Alignment.centerRight,
                                    child: const Icon(
                                      Icons.delete,
                                      color: Colors.white,
                                      size: 20, // Smaller icon for compact design
                                    ),
                                  ),
                                  child: GestureDetector(
                                    onTap: () async {
                                      // Select the chat and switch to its app context
                                      final appProvider = context.read<AppProvider>();
                                      await sessions.selectSession(s.id, s.appId, appProvider: appProvider);
                                      await messageProvider.refreshMessages(dropdownSelected: true);
                                      if (mounted) Navigator.of(context).maybePop();
                                    },
                                    child: AnimatedContainer(
                                      duration: const Duration(milliseconds: 150), // Smooth color transition
                                      width: double.infinity, // Fill the clipped area
                                      height: 50, // Match available space and red background height
                                      padding: const EdgeInsets.symmetric(
                                          horizontal: 16, vertical: 12), // Internal content padding
                                      decoration: BoxDecoration(
                                        color: cardColor, // Use calculated smooth color
                                        borderRadius: isBeingSwiped
                                            ? BorderRadius
                                                .zero // Straight edges when swiping to merge with red background
                                            : BorderRadius.circular(16), // Rounded edges for normal selection
                                      ),
                                      child: Align(
                                        alignment: Alignment.centerLeft,
                                        child: Text(
                                          s.title?.isNotEmpty == true ? s.title! : 'New Chat',
                                          maxLines: 1,
                                          overflow: TextOverflow.ellipsis,
                                          style: const TextStyle(
                                            fontFamily: FontFamily.sFProDisplay,
                                            color: Colors.white,
                                            fontSize: 14.7, // Increased by 5% (14 * 1.05)
                                            fontWeight: FontWeight.w400, // Normal weight like ChatGPT
                                          ),
                                        ),
                                      ),
                                    ),
                                  ),
                                ),
                              ), // Close ClipRRect
                            ), // Close horizontal Padding
                          ), // Close bottom spacing Padding
                        ); // Close SizedBox
                      },
                    ),
                  ),
              ],
            );
          },
        ),
      ),
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
      onSelected: (String? val) => _handleAppSelection(val, provider),
      itemBuilder: (BuildContext context) {
        return _getAppsDropdownItems(context, provider);
      },
      color: const Color(0xFF1F1F25),
    );
  }

  String _getAppNameById(String? appId) {
    if (appId == null || appId == 'omi') {
      return 'Omi';
    }
    final app = context.read<AppProvider>().apps.firstWhereOrNull((app) => app.id == appId);
    return app?.name ?? 'Unknown App';
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
        value: 'omi',
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
                        if (mounted) {
                          context.read<MessageProvider>().captureImage();
                        }
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
                        if (mounted) {
                          context.read<MessageProvider>().selectImage();
                        }
                      },
                    ),
                    _buildDivider(),
                    _buildIOSActionItem(
                      title: "Choose File",
                      icon: Icons.folder,
                      onTap: () {
                        HapticFeedback.selectionClick();
                        Navigator.pop(context);
                        if (mounted) {
                          context.read<MessageProvider>().selectFile();
                        }
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
}
