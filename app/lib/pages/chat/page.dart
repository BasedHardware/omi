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
import 'package:omi/pages/apps/widgets/capability_apps_page.dart';
import 'package:omi/pages/chat/select_text_screen.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/pages/chat/widgets/user_message.dart';
import 'package:omi/pages/chat/widgets/voice_recorder_widget.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/extensions/string.dart';
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

class ChatPageState extends State<ChatPage> with AutomaticKeepAliveClientMixin, TickerProviderStateMixin {
  TextEditingController textController = TextEditingController();
  late ScrollController scrollController;
  late FocusNode textFieldFocusNode;

  bool isScrollingDown = false;

  bool _showVoiceRecorder = false;
  bool _isInitialLoad = true;

  var prefs = SharedPreferencesUtil();
  late List<App> apps;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  // Track which app is pending deletion confirmation
  String? _pendingDeleteAppId;

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
      // Fetch enabled chat apps
      provider.fetchChatApps();
      scrollToBottom();
      // Auto-focus the text field only on initial load, not on app switches
      if (_isInitialLoad) {
        Future.delayed(const Duration(milliseconds: 300), () {
          if (mounted && !_showVoiceRecorder && _isInitialLoad) {
            textFieldFocusNode.requestFocus();
          }
        });
      }
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
          endDrawer: _buildChatAppsEndDrawer(context),
          onEndDrawerChanged: (isOpened) {
            if (isOpened) {
              // Unfocus text field when drawer opens
              textFieldFocusNode.unfocus();
            }
          },
          body: GestureDetector(
            onTap: () {
              // Hide keyboard when tapping outside textfield
              FocusScope.of(context).unfocus();
            },
            child: Column(
              children: [
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
                                        padding: EdgeInsets.only(bottom: bottomPadding, top: topPadding),
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
                // Send message area - fixed at bottom
                Container(
                  margin: const EdgeInsets.only(top: 10),
                  decoration: const BoxDecoration(
                    color: Colors.transparent,
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
                            left: 8,
                            right: 8,
                            top: provider.selectedFiles.isNotEmpty ? 0 : 8,
                            bottom: widget.isPivotBottom ? 20 : (textFieldFocusNode.hasFocus ? 10 : 40),
                          ),
                          child: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                            decoration: BoxDecoration(
                              color: const Color(0xFF2A2A2F),
                              borderRadius: BorderRadius.circular(32),
                            ),
                            child: Row(
                              crossAxisAlignment: CrossAxisAlignment.end,
                              children: [
                                // Plus button
                                if (shouldShowMenuButton())
                                  GestureDetector(
                                    onTap: () {
                                      HapticFeedback.lightImpact();
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
                                      height: 44,
                                      width: 44,
                                      decoration: BoxDecoration(
                                        color: const Color(0xFF3C3C43),
                                        shape: BoxShape.circle,
                                      ),
                                      child: Center(
                                        child: FaIcon(
                                          FontAwesomeIcons.plus,
                                          color: provider.selectedFiles.length > 3 ? Colors.grey : Colors.white,
                                          size: 18,
                                        ),
                                      ),
                                    ),
                                  ),
                                const SizedBox(width: 12),
                                // Text field
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
                                      : TextField(
                                          enabled: true,
                                          controller: textController,
                                          focusNode: textFieldFocusNode,
                                          obscureText: false,
                                          textAlign: TextAlign.start,
                                          textAlignVertical: TextAlignVertical.center,
                                          decoration: const InputDecoration(
                                            hintText: 'Ask anything',
                                            hintStyle: TextStyle(fontSize: 16.0, color: Colors.grey),
                                            focusedBorder: InputBorder.none,
                                            enabledBorder: InputBorder.none,
                                            contentPadding: EdgeInsets.symmetric(horizontal: 4, vertical: 12),
                                            isDense: true,
                                          ),
                                          minLines: 1,
                                          maxLines: 10,
                                          keyboardType: TextInputType.multiline,
                                          textCapitalization: TextCapitalization.sentences,
                                          style: const TextStyle(fontSize: 16.0, color: Colors.white, height: 1.4),
                                        ),
                                ),
                                // Microphone button
                                if (shouldShowVoiceRecorderButton() && textController.text.isEmpty)
                                  GestureDetector(
                                    onTap: () {
                                      HapticFeedback.lightImpact();
                                      FocusScope.of(context).unfocus();
                                      setState(() {
                                        _showVoiceRecorder = true;
                                      });
                                    },
                                    child: Container(
                                      height: 44,
                                      width: 44,
                                      alignment: Alignment.center,
                                      child: const FaIcon(
                                        FontAwesomeIcons.microphone,
                                        color: Colors.grey,
                                        size: 20,
                                      ),
                                    ),
                                  ),
                                // Send button - only show when there's text
                                if (shouldShowSendButton(provider))
                                  ValueListenableBuilder<TextEditingValue>(
                                    valueListenable: textController,
                                    builder: (context, value, child) {
                                      bool hasText = value.text.trim().isNotEmpty;
                                      if (!hasText) return const SizedBox.shrink();

                                      bool canSend = hasText &&
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
                                          decoration: const BoxDecoration(
                                            color: Colors.white,
                                            shape: BoxShape.circle,
                                          ),
                                          child: const Center(
                                            child: FaIcon(
                                              FontAwesomeIcons.arrowUp,
                                              color: Color(0xFF1f1f25),
                                              size: 18,
                                            ),
                                          ),
                                        ),
                                      );
                                    },
                                  ),
                              ],
                            ),
                          ),
                        ),
                      ],
                    );
                  }),
                ),
              ],
            ),
          ),
        );
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
      scrollToBottom();
      context.read<MessageProvider>().setSendingMessage(false);
    }
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

    // enable apps - navigate to chat capability apps page
    if (val == 'enable') {
      _navigateToChatAppsPage();
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

  Future<void> _navigateToChatAppsPage() async {
    if (!mounted) return;

    MixpanelManager().pageOpened('Chat Apps');
    // Navigate to chat capability apps page
    await routeToPage(
      context,
      CapabilityAppsPage(
        capability: AppCapability(id: 'chat', title: 'Chat Assistants'),
        apps: const [],
      ),
    );

    // Refresh chat apps when returning from the page
    if (mounted) {
      _refreshChatAppsFromLocal();
    }
  }

  void _refreshChatAppsFromLocal() {
    // Get enabled chat apps from local AppProvider immediately
    final appProvider = context.read<AppProvider>();
    final messageProvider = context.read<MessageProvider>();

    // Filter apps that are enabled and work with chat
    final localChatApps = appProvider.apps.where((app) => app.enabled && app.worksWithChat()).toList();

    // Update immediately with local data
    messageProvider.chatApps = localChatApps;
    messageProvider.notifyListeners();
  }

  Future<void> _handleAppUninstall(String appId, AppProvider appProvider, MessageProvider messageProvider) async {
    if (!mounted) return;

    // Immediately remove from local chat apps list for instant visual feedback
    messageProvider.chatApps.removeWhere((app) => app.id == appId);
    messageProvider.notifyListeners();

    // Disable the app on server (runs in background)
    appProvider.toggleApp(appId, false, null);
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

    // Add a small delay to let the keyboard animation complete
    // This prevents the widget from being unmounted during the keyboard transition
    await Future.delayed(const Duration(milliseconds: 100));

    // Check if widget is still mounted after delay
    if (!mounted) return;

    // Perform async operation
    await messageProvider.refreshMessages(dropdownSelected: true);

    // Check if widget is still mounted before proceeding
    if (!mounted) return;

    // Get the selected app and send initial message if needed
    var app = appProvider.getSelectedApp();
    if (messageProvider.messages.isEmpty) {
      messageProvider.sendInitialAppMessage(app);
    }
  }

  PreferredSizeWidget _buildAppBar(BuildContext context, MessageProvider provider) {
    return AppBar(
      backgroundColor: Theme.of(context).colorScheme.surface,
      elevation: 0,
      leading: Container(
        width: 36,
        height: 36,
        margin: const EdgeInsets.all(8),
        decoration: BoxDecoration(
          color: Colors.grey.withOpacity(0.3),
          shape: BoxShape.circle,
        ),
        child: IconButton(
          padding: EdgeInsets.zero,
          icon: const Icon(Icons.arrow_back_ios_new, color: Colors.white, size: 18),
          onPressed: () {
            HapticFeedback.mediumImpact();
            Navigator.of(context).pop();
          },
        ),
      ),
      title: Consumer<AppProvider>(
        builder: (context, appProvider, child) {
          return _buildSelectedAppDisplay(context, appProvider);
        },
      ),
      centerTitle: true,
      actions: [
        Container(
          width: 36,
          height: 36,
          margin: const EdgeInsets.only(right: 8),
          decoration: BoxDecoration(
            color: Colors.grey.withOpacity(0.3),
            shape: BoxShape.circle,
          ),
          child: IconButton(
            padding: EdgeInsets.zero,
            icon: const Icon(Icons.extension, color: Colors.white, size: 18),
            onPressed: () {
              HapticFeedback.mediumImpact();
              // Dismiss keyboard before opening drawer
              FocusScope.of(context).unfocus();
              // Use post-frame callback to ensure scaffold state is ready
              WidgetsBinding.instance.addPostFrameCallback((_) {
                scaffoldKey.currentState?.openEndDrawer();
              });
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

  Widget _buildSelectedAppDisplay(BuildContext context, AppProvider provider) {
    final messageProvider = Provider.of<MessageProvider>(context, listen: false);
    var selectedApp = messageProvider.chatApps.firstWhereOrNull((app) => app.id == provider.selectedChatAppId);

    return Row(
      crossAxisAlignment: CrossAxisAlignment.center,
      mainAxisAlignment: MainAxisAlignment.center,
      mainAxisSize: MainAxisSize.min,
      children: [
        selectedApp != null ? _getAppAvatar(selectedApp) : _getOmiAvatar(),
        const SizedBox(width: 8),
        Container(
          constraints: const BoxConstraints(maxWidth: 140),
          child: Text(
            selectedApp != null ? selectedApp.getName() : "Omi",
            style: const TextStyle(color: Colors.white, fontSize: 16),
            overflow: TextOverflow.ellipsis,
          ),
        ),
      ],
    );
  }

  Widget _buildChatAppsEndDrawer(BuildContext context) {
    return Drawer(
      backgroundColor: const Color(0xFF1F1F25),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(20),
          bottomLeft: Radius.circular(20),
        ),
      ),
      child: SafeArea(
        child: Consumer2<MessageProvider, AppProvider>(
          builder: (context, messageProvider, appProvider, child) {
            final chatApps = messageProvider.chatApps;
            final selectedAppId = appProvider.selectedChatAppId;
            final isOmiSelected = chatApps.firstWhereOrNull((a) => a.id == selectedAppId) == null;

            return Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header
                Padding(
                  padding: const EdgeInsets.fromLTRB(20, 16, 16, 8),
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text(
                        'Chat Apps',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 20,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      IconButton(
                        icon: const Padding(
                          padding: EdgeInsets.only(left: 2, top: 1),
                          child: FaIcon(FontAwesomeIcons.xmark, color: Colors.white60, size: 18),
                        ),
                        onPressed: () => Navigator.of(context).pop(),
                      ),
                    ],
                  ),
                ),
                const Divider(color: Colors.white12, height: 1),
                // Actions
                ListTile(
                  leading: const Padding(
                    padding: EdgeInsets.only(left: 2, top: 1),
                    child: FaIcon(FontAwesomeIcons.solidTrashCan, color: Colors.redAccent, size: 20),
                  ),
                  title: const Text(
                    'Clear Chat',
                    style: TextStyle(color: Colors.redAccent, fontSize: 16),
                  ),
                  onTap: () {
                    Navigator.of(context).pop();
                    _handleAppSelection('clear_chat', appProvider);
                  },
                ),
                ListTile(
                  leading: const Padding(
                    padding: EdgeInsets.only(left: 2, top: 1),
                    child: FaIcon(FontAwesomeIcons.circlePlus, color: Colors.white, size: 20),
                  ),
                  title: const Text(
                    'Enable Apps',
                    style: TextStyle(color: Colors.white, fontSize: 16),
                  ),
                  trailing: const Padding(
                    padding: EdgeInsets.only(left: 2, top: 1),
                    child: FaIcon(FontAwesomeIcons.chevronRight, color: Colors.white38, size: 14),
                  ),
                  onTap: () {
                    Navigator.of(context).pop();
                    _navigateToChatAppsPage();
                  },
                ),
                const Divider(color: Colors.white12, height: 1),
                const Padding(
                  padding: EdgeInsets.fromLTRB(16, 16, 20, 8),
                  child: Text(
                    'Select App',
                    style: TextStyle(
                      color: Colors.white60,
                      fontSize: 13,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                ),
                // App list
                Expanded(
                  child: ListView(
                    padding: EdgeInsets.zero,
                    children: [
                      // Omi option
                      _buildDrawerAppItem(
                        avatar: _getOmiAvatar(),
                        name: 'Omi',
                        isSelected: isOmiSelected,
                        onTap: () {
                          Navigator.of(context).pop();
                          _handleAppSelection('no_selected', appProvider);
                        },
                      ),
                      // Enabled chat apps
                      ...chatApps.map((app) => _buildDrawerAppItem(
                            avatar: _getAppAvatar(app),
                            name: app.getName(),
                            isSelected: selectedAppId == app.id,
                            appId: app.id,
                            onTap: () {
                              Navigator.of(context).pop();
                              _handleAppSelection(app.id, appProvider);
                            },
                            onConfirmDelete: selectedAppId != app.id
                                ? () => _handleAppUninstall(app.id, appProvider, messageProvider)
                                : null,
                          )),
                      if (chatApps.isEmpty)
                        const Padding(
                          padding: EdgeInsets.all(20),
                          child: Text(
                            'No chat apps enabled.\nTap "Enable Apps" to add some.',
                            style: TextStyle(color: Colors.white38, fontSize: 14),
                            textAlign: TextAlign.center,
                          ),
                        ),
                    ],
                  ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _buildDrawerAppItem({
    required Widget avatar,
    required String name,
    required bool isSelected,
    required VoidCallback onTap,
    String? appId,
    VoidCallback? onConfirmDelete,
  }) {
    final bool isPendingDelete = appId != null && _pendingDeleteAppId == appId;

    if (isPendingDelete) {
      // Show inline confirmation buttons - match ListTile height (56px)
      return Container(
        height: 56,
        padding: const EdgeInsets.symmetric(horizontal: 16),
        child: Row(
          children: [
            avatar,
            const SizedBox(width: 12),
            Expanded(
              child: Text(
                name,
                style: const TextStyle(color: Colors.white, fontSize: 16),
                overflow: TextOverflow.ellipsis,
              ),
            ),
            const SizedBox(width: 8),
            // Cancel button (white)
            GestureDetector(
              onTap: () {
                setState(() {
                  _pendingDeleteAppId = null;
                });
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Text(
                  'Cancel',
                  style: TextStyle(
                    color: Colors.black,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 8),
            // Disable button (red)
            GestureDetector(
              onTap: () {
                setState(() {
                  _pendingDeleteAppId = null;
                });
                onConfirmDelete?.call();
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: Colors.redAccent,
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Text(
                  'Disable',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 13,
                    fontWeight: FontWeight.w500,
                  ),
                ),
              ),
            ),
          ],
        ),
      );
    }

    return ListTile(
      leading: avatar,
      title: Text(
        name,
        style: const TextStyle(color: Colors.white, fontSize: 16),
        overflow: TextOverflow.ellipsis,
      ),
      trailing: isSelected
          ? const Padding(
              padding: EdgeInsets.only(left: 2, top: 1),
              child: FaIcon(FontAwesomeIcons.solidCircleCheck, color: Colors.white, size: 18),
            )
          : appId != null && onConfirmDelete != null
              ? GestureDetector(
                  onTap: () {
                    setState(() {
                      _pendingDeleteAppId = appId;
                    });
                  },
                  child: const Padding(
                    padding: EdgeInsets.only(left: 2, top: 1),
                    child: FaIcon(FontAwesomeIcons.solidTrashCan, color: Colors.white38, size: 16),
                  ),
                )
              : null,
      selected: isSelected,
      selectedTileColor: Colors.white.withOpacity(0.1),
      onTap: onTap,
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
