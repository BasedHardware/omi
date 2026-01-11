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
import 'package:omi/pages/chat/widgets/markdown_message_widget.dart';
import 'package:omi/desktop/pages/chat/widgets/desktop_voice_recorder_widget.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/ui/atoms/omi_typing_indicator.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';
import 'package:shimmer/shimmer.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:omi/ui/atoms/omi_avatar.dart';
import 'package:omi/ui/molecules/omi_chat_bubble.dart';
import 'package:omi/ui/atoms/omi_message_input.dart';
import 'package:omi/ui/atoms/omi_send_button.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/ui/molecules/omi_section_header.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'widgets/desktop_message_action_menu.dart';

class DesktopChatPage extends StatefulWidget {
  const DesktopChatPage({super.key});

  @override
  State<DesktopChatPage> createState() => DesktopChatPageState();
}

class DesktopChatPageState extends State<DesktopChatPage> with AutomaticKeepAliveClientMixin, TickerProviderStateMixin {
  TextEditingController textController = TextEditingController();
  late ScrollController scrollController;
  late AnimationController _fadeController;
  late AnimationController _slideController;
  late AnimationController _pulseController;

  static final RegExp _contextRegex = RegExp(r'^Context: "([\s\S]+?)"\n\n');

  late Animation<double> _fadeAnimation;
  late Animation<Offset> _slideAnimation;
  late Animation<double> _pulseAnimation;

  bool _animationsInitialized = false;

  bool isScrollingDown = false;
  bool _showVoiceRecorder = false;

  var prefs = SharedPreferencesUtil();
  late List<App> apps;

  // GlobalKey for the add button to get its position
  final GlobalKey _addButtonKey = GlobalKey();

  late FocusNode _focusNode;
  late FocusNode _inputFocusNode;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    apps = prefs.appsList;
    scrollController = ScrollController(initialScrollOffset: 1e9);
    _focusNode = FocusNode();
    _inputFocusNode = FocusNode(onKeyEvent: (node, event) {
      if (event is KeyDownEvent && event.logicalKey == LogicalKeyboardKey.enter) {
        if (HardwareKeyboard.instance.isShiftPressed) {
          return KeyEventResult.ignored;
        }
        if (textController.text.trim().isEmpty) {
          return KeyEventResult.handled;
        }
        _sendMessageUtil(textController.text.trim());
        return KeyEventResult.handled;
      }
      return KeyEventResult.ignored;
    });

    _fadeController = AnimationController(
      duration: const Duration(milliseconds: 800),
      vsync: this,
    );

    _slideController = AnimationController(
      duration: const Duration(milliseconds: 600),
      vsync: this,
    );

    _pulseController = AnimationController(
      duration: const Duration(milliseconds: 2000),
      vsync: this,
    )..repeat(reverse: true);

    _fadeAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _fadeController, curve: Curves.easeOutCubic),
    );

    _slideAnimation = Tween<Offset>(
      begin: const Offset(0, 0.3),
      end: Offset.zero,
    ).animate(CurvedAnimation(parent: _slideController, curve: Curves.easeOutCubic));

    _pulseAnimation = Tween<double>(begin: 0.0, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );

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

    _animationsInitialized = true;

    SchedulerBinding.instance.addPostFrameCallback((_) async {
      var provider = context.read<MessageProvider>();
      if (provider.messages.isEmpty) {
        provider.refreshMessages();
      }

      _fadeController.forward();
      _slideController.forward();

      scrollToBottom();
    });
    super.initState();
  }

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    _requestFocusIfPossible();
  }

  void _requestFocusIfPossible() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _focusNode.canRequestFocus) {
        _focusNode.requestFocus();
      }
    });
  }

  Future<void> _handleReload() async {
    final messageProvider = context.read<MessageProvider>();
    if (!messageProvider.isLoadingMessages) {
      messageProvider.refreshMessages();
    }
  }

  @override
  void dispose() {
    textController.dispose();
    scrollController.dispose();
    _fadeController.dispose();
    _slideController.dispose();
    _pulseController.dispose();
    _focusNode.dispose();
    _inputFocusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);

    return VisibilityDetector(
        key: const Key('desktop-chat-page'),
        onVisibilityChanged: (visibilityInfo) {
          if (visibilityInfo.visibleFraction > 0.1) {
            _requestFocusIfPossible();
          }
        },
        child: CallbackShortcuts(
          bindings: {
            const SingleActivator(LogicalKeyboardKey.keyR, meta: true): _handleReload,
          },
          child: Focus(
            focusNode: _focusNode,
            autofocus: true,
            child: GestureDetector(
              onTap: () {
                if (!_focusNode.hasFocus) {
                  _focusNode.requestFocus();
                }
              },
              child: Consumer3<MessageProvider, ConnectivityProvider, AppProvider>(
                builder: (context, provider, connectivityProvider, appProvider, child) {
                  return Container(
                    decoration: BoxDecoration(
                      gradient: LinearGradient(
                        begin: Alignment.topCenter,
                        end: Alignment.bottomCenter,
                        colors: [
                          ResponsiveHelper.backgroundPrimary,
                          ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.8),
                        ],
                      ),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: ClipRRect(
                      borderRadius: BorderRadius.circular(20),
                      child: Stack(
                        children: [
                          _buildAnimatedBackground(),

                          // Main content with glassmorphism
                          Container(
                            decoration: BoxDecoration(
                              color: Colors.white.withValues(alpha: 0.02),
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: Column(
                              children: [
                                _buildModernHeader(appProvider),
                                if (provider.isLoadingMessages) _buildLoadingBar(),
                                Expanded(
                                  child: _animationsInitialized
                                      ? FadeTransition(
                                          opacity: _fadeAnimation,
                                          child: SlideTransition(
                                            position: _slideAnimation,
                                            child: _buildChatContent(provider, connectivityProvider),
                                          ),
                                        )
                                      : _buildChatContent(provider, connectivityProvider),
                                ),
                                _buildFloatingInputArea(provider, connectivityProvider),
                              ],
                            ),
                          ),
                        ],
                      ),
                    ),
                  );
                },
              ),
            ),
          ),
        ));
  }

  Widget _buildAnimatedBackground() {
    if (!_animationsInitialized) {
      return Container(
        decoration: BoxDecoration(
          gradient: RadialGradient(
            center: Alignment.topRight,
            radius: 2.0,
            colors: [
              ResponsiveHelper.purplePrimary.withValues(alpha: 0.05),
              Colors.transparent,
            ],
          ),
        ),
      );
    }

    return AnimatedBuilder(
      animation: _pulseAnimation,
      builder: (context, child) {
        return Container(
          decoration: BoxDecoration(
            gradient: RadialGradient(
              center: Alignment.topRight,
              radius: 2.0,
              colors: [
                ResponsiveHelper.purplePrimary.withValues(alpha: 0.05 + _pulseAnimation.value * 0.03),
                Colors.transparent,
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildModernHeader(AppProvider appProvider) {
    final selectedApp = appProvider.selectedChatAppId.isEmpty || appProvider.selectedChatAppId == 'no_selected'
        ? null
        : appProvider.getSelectedApp();

    return Container(
      padding: const EdgeInsets.fromLTRB(20, 16, 20, 12),
      child: Row(
        children: [
          // App selection dropdown
          Expanded(
            child: Material(
              color: Colors.transparent,
              child: InkWell(
                onTap: () => _showAppSelectionSheet(context, appProvider),
                borderRadius: BorderRadius.circular(12),
                child: Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: ResponsiveHelper.backgroundQuaternary.withValues(alpha: 0.3),
                      width: 1,
                    ),
                  ),
                  child: Row(
                    children: [
                      // App avatar
                      selectedApp != null
                          ? OmiAvatar(
                              size: 24,
                              imageUrl: selectedApp.getImageUrl(),
                            )
                          : OmiAvatar(
                              size: 24,
                              fallback: Image.asset(Assets.images.logoTransparent.path),
                            ),

                      const SizedBox(width: 12),

                      // App name and description
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              selectedApp?.name ?? 'Omi',
                              style: const TextStyle(
                                color: ResponsiveHelper.textPrimary,
                                fontSize: 14,
                                fontWeight: FontWeight.w600,
                              ),
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                            ),
                            if (selectedApp != null) ...[
                              const SizedBox(height: 2),
                              Text(
                                'Chat with ${selectedApp.name}',
                                style: const TextStyle(
                                  color: ResponsiveHelper.textTertiary,
                                  fontSize: 11,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ] else ...[
                              const SizedBox(height: 2),
                              const Text(
                                'Default AI Assistant',
                                style: TextStyle(
                                  color: ResponsiveHelper.textTertiary,
                                  fontSize: 11,
                                ),
                              ),
                            ],
                          ],
                        ),
                      ),

                      const SizedBox(width: 8),

                      // Dropdown arrow
                      const Icon(
                        FontAwesomeIcons.chevronDown,
                        color: ResponsiveHelper.textSecondary,
                        size: 12,
                      ),
                    ],
                  ),
                ),
              ),
            ),
          ),

          const SizedBox(width: 12),

          // Clear chat button
          Material(
            color: Colors.transparent,
            child: InkWell(
              onTap: () => _showClearChatDialog(context),
              borderRadius: BorderRadius.circular(12),
              child: Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.6),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  FontAwesomeIcons.trash,
                  color: ResponsiveHelper.textSecondary,
                  size: 16,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildLoadingBar() {
    return Container(
      height: 3,
      margin: const EdgeInsets.only(bottom: 8),
      decoration: const BoxDecoration(
        borderRadius: BorderRadius.only(
          topLeft: Radius.circular(20),
          topRight: Radius.circular(20),
        ),
      ),
      child: Stack(
        children: [
          Container(
            decoration: BoxDecoration(
              gradient: LinearGradient(
                colors: [
                  ResponsiveHelper.purplePrimary.withValues(alpha: 0.3),
                  ResponsiveHelper.purplePrimary,
                  ResponsiveHelper.purplePrimary.withValues(alpha: 0.3),
                ],
              ),
              borderRadius: BorderRadius.circular(3),
            ),
          ),
          const LinearProgressIndicator(
            backgroundColor: Colors.transparent,
            valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
          ),
        ],
      ),
    );
  }

  Widget _buildChatContent(
    MessageProvider provider,
    ConnectivityProvider connectivityProvider,
  ) {
    if (provider.isLoadingMessages && !provider.hasCachedMessages) {
      return _buildLoadingState(provider.firstTimeLoadingText);
    }

    if (provider.isClearingChat) {
      return _buildLoadingState("Deleting your messages from Omi's memory...");
    }

    if (provider.messages.isEmpty) {
      return _buildEmptyState(connectivityProvider.isConnected);
    }

    return _buildMessagesList(provider);
  }

  Widget _buildLoadingState(String text) {
    Widget content = Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.8),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: Colors.white.withValues(alpha: 0.1),
              width: 1,
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.1),
                blurRadius: 20,
                offset: const Offset(0, 10),
              ),
            ],
          ),
          child: Column(
            children: [
              _animationsInitialized
                  ? AnimatedBuilder(
                      animation: _pulseController,
                      builder: (context, child) {
                        return Transform.scale(
                          scale: 1.0 + (_pulseAnimation.value * 0.1),
                          child: Container(
                            width: 40,
                            height: 40,
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                colors: [
                                  ResponsiveHelper.purplePrimary,
                                  ResponsiveHelper.purplePrimary.withValues(alpha: 0.7),
                                ],
                              ),
                              borderRadius: BorderRadius.circular(20),
                            ),
                            child: const CircularProgressIndicator(
                              valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                              strokeWidth: 2,
                            ),
                          ),
                        );
                      },
                    )
                  : Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        gradient: LinearGradient(
                          colors: [
                            ResponsiveHelper.purplePrimary,
                            ResponsiveHelper.purplePrimary.withValues(alpha: 0.7),
                          ],
                        ),
                        borderRadius: BorderRadius.circular(20),
                      ),
                      child: const CircularProgressIndicator(
                        valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                        strokeWidth: 2,
                      ),
                    ),
              const SizedBox(height: 16),
              Text(
                text,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: ResponsiveHelper.textSecondary,
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                ),
              ),
            ],
          ),
        ),
      ],
    );

    return Center(
      child: _animationsInitialized
          ? FadeTransition(
              opacity: _fadeAnimation,
              child: content,
            )
          : content,
    );
  }

  Widget _buildEmptyState(bool isConnected) {
    Widget content = Container(
      padding: const EdgeInsets.all(40),
      margin: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.6),
            ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.4),
          ],
        ),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: Colors.white.withValues(alpha: 0.1),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.1),
            blurRadius: 30,
            offset: const Offset(0, 15),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _animationsInitialized
              ? AnimatedBuilder(
                  animation: _pulseController,
                  builder: (context, child) {
                    return Transform.scale(
                      scale: 1.0 + (_pulseAnimation.value * 0.05),
                      child: Container(
                        padding: const EdgeInsets.all(20),
                        decoration: BoxDecoration(
                          gradient: LinearGradient(
                            colors: [
                              ResponsiveHelper.purplePrimary.withValues(alpha: 0.2),
                              ResponsiveHelper.purplePrimary.withValues(alpha: 0.1),
                            ],
                          ),
                          borderRadius: BorderRadius.circular(20),
                        ),
                        child: Icon(
                          isConnected ? Icons.chat_bubble_outline_rounded : Icons.wifi_off_rounded,
                          size: 48,
                          color: ResponsiveHelper.purplePrimary,
                        ),
                      ),
                    );
                  },
                )
              : Container(
                  padding: const EdgeInsets.all(20),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [
                        ResponsiveHelper.purplePrimary.withValues(alpha: 0.2),
                        ResponsiveHelper.purplePrimary.withValues(alpha: 0.1),
                      ],
                    ),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Icon(
                    isConnected ? Icons.chat_bubble_outline_rounded : Icons.wifi_off_rounded,
                    size: 48,
                    color: ResponsiveHelper.purplePrimary,
                  ),
                ),
          const SizedBox(height: 24),
          Text(
            isConnected ? '✨ Ready to chat!' : '🌐 Connection needed',
            style: const TextStyle(
              color: ResponsiveHelper.textPrimary,
              fontSize: 20,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            isConnected ? 'Start a conversation and let the magic begin' : 'Please check your internet connection',
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: ResponsiveHelper.textSecondary,
              fontSize: 14,
              height: 1.5,
            ),
          ),
        ],
      ),
    );

    return Center(
      child: _animationsInitialized
          ? FadeTransition(
              opacity: _fadeAnimation,
              child: content,
            )
          : content,
    );
  }

  Widget _buildMessagesList(MessageProvider provider) {
    return ListView.builder(
      reverse: false,
      controller: scrollController,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      itemCount: provider.messages.length,
      itemBuilder: (context, chatIndex) {
        final message = provider.messages[chatIndex];
        double topPadding = chatIndex == provider.messages.length - 1 ? 16 : 16;
        if (chatIndex != provider.messages.length - 1) message.askForNps = false;

        double bottomPadding = 0;

        Widget messageWidget = Container(
          margin: EdgeInsets.only(
            bottom: bottomPadding,
            top: topPadding,
          ),
          child: GestureDetector(
            onLongPress: () => _showMessageActionMenu(context, message),
            child: _buildModernMessageBubble(message, provider, chatIndex),
          ),
        );

        return AnimatedContainer(
          duration: Duration(milliseconds: 300 + (chatIndex * 50)),
          curve: Curves.easeOutCubic,
          child: _animationsInitialized
              ? FadeTransition(
                  opacity: _fadeAnimation,
                  child: SlideTransition(
                    position: Tween<Offset>(
                      begin: Offset(0, 0.1 + (chatIndex * 0.02)),
                      end: Offset.zero,
                    ).animate(CurvedAnimation(
                      parent: _slideController,
                      curve: Interval(
                        (chatIndex * 0.1).clamp(0.0, 0.8),
                        1.0,
                        curve: Curves.easeOutCubic,
                      ),
                    )),
                    child: messageWidget,
                  ),
                )
              : messageWidget,
        );
      },
    );
  }

  Widget _buildModernMessageBubble(ServerMessage message, MessageProvider provider, int chatIndex) {
    // Make messages take only 70% of available width and align based on sender
    String text = message.text.decodeString;
    String? contextText;
    String messageText = text;

    if (message.sender == MessageSender.human) {
      final match = _contextRegex.firstMatch(text);

      if (match != null) {
        contextText = match.group(1);
        messageText = text.substring(match.end);
      }
    }

    return Align(
      alignment: message.sender == MessageSender.ai ? Alignment.centerLeft : Alignment.centerRight,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.7 * 0.7, // 70% of available chat width
        ),
        child: message.sender == MessageSender.ai
            ? Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      OmiAvatar(
                        size: 32,
                        imageUrl: provider.messageSenderApp(message.appId)?.getImageUrl(),
                        fallback: Image.asset(Assets.images.herologo.path, height: 24, width: 24),
                      ),
                      const SizedBox(width: 12),
                      // AI message bubble
                      Expanded(
                        child: OmiChatBubble(
                          type: OmiChatBubbleType.incoming,
                          child: _buildAIMessageContent(message, provider, chatIndex),
                        ),
                      ),
                    ],
                  ),
                  Container(
                    margin: const EdgeInsets.only(left: 50, top: 6),
                    child: Text(
                      formatChatTimestamp(message.createdAt),
                      style: TextStyle(
                        color: ResponsiveHelper.textTertiary.withValues(alpha: 0.5),
                        fontSize: 11,
                        fontWeight: FontWeight.w400,
                      ),
                    ),
                  ),
                ],
              )
            : Column(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  if (contextText != null)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 6.0, right: 4.0),
                      child: Container(
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                        decoration: BoxDecoration(
                          color: ResponsiveHelper.backgroundTertiary.withValues(alpha: 0.5),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(
                            color: ResponsiveHelper.backgroundQuaternary.withValues(alpha: 0.5),
                            width: 1,
                          ),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            const Icon(Icons.subdirectory_arrow_right,
                                size: 14, color: ResponsiveHelper.textSecondary),
                            const SizedBox(width: 8),
                            Flexible(
                              child: Text(
                                contextText,
                                style: const TextStyle(
                                  color: ResponsiveHelper.textSecondary,
                                  fontSize: 12,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  OmiChatBubble(
                    type: OmiChatBubbleType.outgoing,
                    child: Text(
                      messageText.trimRight(),
                      style: const TextStyle(
                        color: ResponsiveHelper.textPrimary,
                        fontSize: 15,
                        height: 1.4,
                      ),
                    ),
                  ),
                  const SizedBox(height: 5),
                ],
              ),
      ),
    );
  }

  Widget _buildAIMessageContent(ServerMessage message, MessageProvider provider, int chatIndex) {
    // Custom AI message content without profile picture and timestamp
    if (message.memories.isNotEmpty) {
      return MemoriesMessageWidget(
        showTypingIndicator: provider.showTypingIndicator && chatIndex == provider.messages.length - 1,
        messageMemories: message.memories.length > 3 ? message.memories.sublist(0, 3) : message.memories,
        messageText: message.isEmpty ? '...' : message.text.decodeString,
        updateConversation: (ServerConversation conversation) {
          context.read<ConversationProvider>().updateConversation(conversation);
        },
        message: message,
        setMessageNps: (int value, {String? reason}) {
          provider.setMessageNps(message, value, reason: reason);
        },
        date: message.createdAt,
      );
    } else if (message.type == MessageType.daySummary) {
      return DaySummaryWidget(
        showTypingIndicator: provider.showTypingIndicator && chatIndex == provider.messages.length - 1,
        messageText: message.text.decodeString,
        date: message.createdAt,
      );
    } else if (provider.messages.length <= 1 && provider.messageSenderApp(message.appId)?.isNotPersona() == true) {
      return InitialMessageWidget(
        showTypingIndicator: provider.showTypingIndicator && chatIndex == provider.messages.length - 1,
        messageText: message.text.decodeString,
        sendMessage: _sendMessageUtil,
      );
    } else {
      // Custom normal message widget without timestamp
      return _buildCustomNormalMessageWidget(message, provider, chatIndex);
    }
  }

  Widget _buildCustomNormalMessageWidget(ServerMessage message, MessageProvider provider, int chatIndex) {
    var previousThinkingText = message.thinkings.length > 1
        ? message.thinkings
            .sublist(message.thinkings.length - 2 >= 0 ? message.thinkings.length - 2 : 0)
            .first
            .decodeString
        : null;
    var thinkingText = message.thinkings.isNotEmpty ? message.thinkings.last.decodeString : null;
    bool showTypingIndicator = provider.showTypingIndicator && chatIndex == provider.messages.length - 1;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisAlignment: MainAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        showTypingIndicator && message.text.isEmpty
            ? Container(
                margin: EdgeInsets.only(top: previousThinkingText != null ? 0 : 8),
                child: Row(
                  children: [
                    thinkingText != null
                        ? Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisAlignment: MainAxisAlignment.start,
                              children: [
                                previousThinkingText != null
                                    ? Text(
                                        overflow: TextOverflow.fade,
                                        maxLines: 1,
                                        softWrap: false,
                                        previousThinkingText,
                                        style: const TextStyle(color: Colors.white60, fontSize: 14),
                                      )
                                    : const SizedBox.shrink(),
                                Shimmer.fromColors(
                                  baseColor: Colors.white,
                                  highlightColor: Colors.grey,
                                  child: Text(
                                    overflow: TextOverflow.fade,
                                    maxLines: 1,
                                    softWrap: false,
                                    thinkingText,
                                    style: const TextStyle(color: Colors.white, fontSize: 14),
                                  ),
                                )
                              ],
                            ),
                          )
                        : const SizedBox(
                            height: 16,
                            child: OmiTypingIndicator(),
                          ),
                  ],
                ))
            : const SizedBox.shrink(),
        message.text.isEmpty ? const SizedBox.shrink() : getMarkdownWidget(context, message.text.decodeString),
        _getNpsWidget(context, message, (int value, {String? reason}) {
          provider.setMessageNps(message, value, reason: reason);
        }),
      ],
    );
  }

  Widget _getNpsWidget(BuildContext context, ServerMessage message, Function(int, {String? reason}) setMessageNps) {
    if (!message.askForNps) return const SizedBox();

    return Padding(
      padding: const EdgeInsetsDirectional.only(top: 8),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          Text('Was this helpful?', style: TextStyle(fontWeight: FontWeight.w500, color: Colors.grey.shade300)),
          const SizedBox(width: 4),
          OmiIconButton(
            icon: Icons.thumb_down_alt_outlined,
            style: OmiIconButtonStyle.neutral,
            size: 28,
            iconSize: 14,
            borderRadius: 6,
            onPressed: () {
              // For desktop, submit thumbs down without reason picker (can be enhanced later)
              setMessageNps(-1);
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: const Text('Thank you for your feedback!'),
                  backgroundColor: ResponsiveHelper.backgroundTertiary,
                  behavior: SnackBarBehavior.floating,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  duration: const Duration(seconds: 2),
                ),
              );
            },
          ),
          const SizedBox(width: 4),
          OmiIconButton(
            icon: Icons.thumb_up_alt_outlined,
            style: OmiIconButtonStyle.neutral,
            size: 28,
            iconSize: 14,
            borderRadius: 6,
            onPressed: () {
              setMessageNps(1);
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: const Text('Thank you for your feedback!'),
                  backgroundColor: ResponsiveHelper.backgroundTertiary,
                  behavior: SnackBarBehavior.floating,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                  duration: const Duration(seconds: 2),
                ),
              );
            },
          ),
        ],
      ),
    );
  }

  Widget _buildFloatingInputArea(
    MessageProvider provider,
    ConnectivityProvider connectivityProvider,
  ) {
    return Container(
      margin: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundSecondary.withValues(alpha: 0.95),
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.1),
            blurRadius: 30,
            offset: const Offset(0, 10),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(24),
        child: Column(
          children: [
            // Modern file preview area
            Consumer<MessageProvider>(builder: (context, provider, child) {
              if (provider.selectedFiles.isNotEmpty) {
                return _buildModernFilePreview(provider);
              }
              return const SizedBox.shrink();
            }),

            // Enhanced input row
            _buildModernInputRow(provider, connectivityProvider),
          ],
        ),
      ),
    );
  }

  Widget _buildModernFilePreview(MessageProvider provider) {
    return Container(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            '📎 Attached Files',
            style: TextStyle(
              color: ResponsiveHelper.textSecondary,
              fontSize: 12,
              fontWeight: FontWeight.w500,
            ),
          ),
          const SizedBox(height: 12),
          SizedBox(
            height: 80,
            child: ListView.builder(
              itemCount: provider.selectedFiles.length,
              scrollDirection: Axis.horizontal,
              shrinkWrap: true,
              itemBuilder: (ctx, idx) {
                return Container(
                  margin: const EdgeInsets.only(right: 12),
                  width: 80,
                  height: 80,
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.backgroundTertiary,
                    image: provider.selectedFileTypes[idx] == 'image'
                        ? DecorationImage(
                            image: FileImage(provider.selectedFiles[idx]),
                            fit: BoxFit.cover,
                          )
                        : null,
                    borderRadius: BorderRadius.circular(16),
                    boxShadow: [
                      BoxShadow(
                        color: Colors.black.withOpacity(0.1),
                        blurRadius: 10,
                        offset: const Offset(0, 4),
                      ),
                    ],
                  ),
                  child: Stack(
                    children: [
                      if (provider.selectedFileTypes[idx] != 'image')
                        Center(
                          child: Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: ResponsiveHelper.purplePrimary.withValues(alpha: 0.2),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: const Icon(
                              Icons.insert_drive_file_rounded,
                              color: ResponsiveHelper.purplePrimary,
                              size: 24,
                            ),
                          ),
                        ),
                      if (provider.isFileUploading(provider.selectedFiles[idx].path))
                        Container(
                          decoration: BoxDecoration(
                            color: Colors.black.withOpacity(0.6),
                            borderRadius: BorderRadius.circular(16),
                          ),
                          child: Center(
                            child: Container(
                              padding: const EdgeInsets.all(8),
                              decoration: BoxDecoration(
                                color: Colors.white.withOpacity(0.1),
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: const SizedBox(
                                width: 20,
                                height: 20,
                                child: CircularProgressIndicator(
                                  valueColor: AlwaysStoppedAnimation<Color>(Colors.white),
                                  strokeWidth: 2,
                                ),
                              ),
                            ),
                          ),
                        ),
                      Positioned(
                        top: 6,
                        right: 6,
                        child: GestureDetector(
                          onTap: () => provider.clearSelectedFile(idx),
                          child: Container(
                            width: 20,
                            height: 20,
                            decoration: BoxDecoration(
                              color: Colors.red.shade500,
                              borderRadius: BorderRadius.circular(10),
                              boxShadow: [
                                BoxShadow(
                                  color: Colors.red.withOpacity(0.3),
                                  blurRadius: 6,
                                  offset: const Offset(0, 2),
                                ),
                              ],
                            ),
                            child: const Icon(
                              Icons.close_rounded,
                              size: 12,
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
          ),
        ],
      ),
    );
  }

  Widget _buildModernInputRow(
    MessageProvider provider,
    ConnectivityProvider connectivityProvider,
  ) {
    return Padding(
      padding: const EdgeInsets.all(12),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          // Enhanced add button
          if (!_showVoiceRecorder) _buildModernAddButton(provider),

          // Modern text input or voice recorder
          Expanded(
            child: _showVoiceRecorder ? _buildEnhancedVoiceRecorder() : _buildModernTextInput(),
          ),

          // Enhanced voice button
          if (!_showVoiceRecorder) _buildModernVoiceButton(),

          // Modern send button with reactive state
          if (!provider.sendingMessage && !_showVoiceRecorder)
            ValueListenableBuilder<TextEditingValue>(
              valueListenable: textController,
              builder: (context, value, child) {
                return _buildModernSendButton(provider, connectivityProvider);
              },
            ),
        ],
      ),
    );
  }

  Widget _buildModernAddButton(MessageProvider provider) {
    bool isDisabled = provider.selectedFiles.length > 3;

    return Container(
      key: _addButtonKey,
      margin: const EdgeInsets.only(right: 8),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: isDisabled ? null : () => _showFileOptionsPopup(context, provider),
          borderRadius: BorderRadius.circular(12),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: isDisabled
                  ? ResponsiveHelper.textQuaternary.withOpacity(0.1)
                  : ResponsiveHelper.purplePrimary.withOpacity(0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(
              Icons.add_rounded,
              color: isDisabled ? ResponsiveHelper.textQuaternary : ResponsiveHelper.purplePrimary,
              size: 20,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildEnhancedVoiceRecorder() {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 8),
      child: DesktopVoiceRecorderWidget(
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
      ),
    );
  }

  Widget _buildModernTextInput() {
    return OmiMessageInput(
      controller: textController,
      focusNode: _inputFocusNode,
    );
  }

  Widget _buildModernVoiceButton() {
    return Container(
      margin: const EdgeInsets.only(left: 8),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: () {
            setState(() {
              _showVoiceRecorder = true;
            });
          },
          borderRadius: BorderRadius.circular(12),
          child: _animationsInitialized
              ? AnimatedBuilder(
                  animation: _pulseController,
                  builder: (context, child) {
                    return Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: ResponsiveHelper.purplePrimary.withOpacity(0.15 + _pulseAnimation.value * 0.05),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Icon(
                        Icons.mic_rounded,
                        color: ResponsiveHelper.purplePrimary,
                        size: 20,
                      ),
                    );
                  },
                )
              : Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: ResponsiveHelper.purplePrimary.withOpacity(0.15),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(
                    Icons.mic_rounded,
                    color: ResponsiveHelper.purplePrimary,
                    size: 20,
                  ),
                ),
        ),
      ),
    );
  }

  Widget _buildModernSendButton(
    MessageProvider provider,
    ConnectivityProvider connectivityProvider,
  ) {
    bool canSend =
        textController.text.trim().isNotEmpty && !provider.isUploadingFiles && connectivityProvider.isConnected;

    return Container(
      margin: const EdgeInsets.only(left: 8),
      child: OmiSendButton(
        enabled: canSend,
        onPressed: canSend
            ? () {
                String message = textController.text.trim();
                if (message.isEmpty) return;
                _sendMessageUtil(message);
              }
            : null,
      ),
    );
  }

  void _showFileOptionsPopup(BuildContext context, MessageProvider provider) {
    if (provider.selectedFiles.length > 3) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: const Text('You can only upload 4 files at a time'),
          backgroundColor: ResponsiveHelper.purplePrimary,
          behavior: SnackBarBehavior.floating,
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          duration: const Duration(seconds: 2),
        ),
      );
      return;
    }

    // Get the position of the add button using the GlobalKey
    final RenderBox? buttonBox = _addButtonKey.currentContext?.findRenderObject() as RenderBox?;
    if (buttonBox == null) return;

    final Offset buttonPosition = buttonBox.localToGlobal(Offset.zero);

    showMenu<String>(
      context: context,
      position: RelativeRect.fromLTRB(
        buttonPosition.dx,
        buttonPosition.dy - (PlatformService.isDesktop ? 160 : 220),
        buttonPosition.dx + 200,
        buttonPosition.dy,
      ),
      color: ResponsiveHelper.backgroundSecondary.withOpacity(0.95),
      elevation: 8,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
      ),
      items: [
        if (PlatformService.isMobile)
          PopupMenuItem<String>(
            value: 'camera',
            padding: EdgeInsets.zero,
            child: _buildPopupFileOption(
              icon: Icons.camera_alt_rounded,
              title: "Take a Photo",
              subtitle: "Capture with camera",
            ),
          ),
        PopupMenuItem<String>(
          value: 'gallery',
          padding: EdgeInsets.zero,
          child: _buildPopupFileOption(
            icon: Icons.photo_library_rounded,
            title: "Select Images",
            subtitle: "Choose from gallery",
          ),
        ),
        PopupMenuItem<String>(
          value: 'file',
          padding: EdgeInsets.zero,
          child: _buildPopupFileOption(
            icon: Icons.attach_file_rounded,
            title: "Select a File",
            subtitle: "Choose any file type",
          ),
        ),
      ],
    ).then((String? result) {
      if (result != null && mounted) {
        switch (result) {
          case 'camera':
            context.read<MessageProvider>().captureImage();
            break;
          case 'gallery':
            context.read<MessageProvider>().selectImage();
            break;
          case 'file':
            context.read<MessageProvider>().selectFile();
            break;
        }
      }
    });
  }

  Widget _buildPopupFileOption({
    required IconData icon,
    required String title,
    required String subtitle,
  }) {
    return Container(
      width: 200,
      padding: const EdgeInsets.all(16),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: ResponsiveHelper.purplePrimary.withOpacity(0.2),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(
              icon,
              color: ResponsiveHelper.purplePrimary,
              size: 20,
            ),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              mainAxisSize: MainAxisSize.min,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: const TextStyle(
                    color: ResponsiveHelper.textSecondary,
                    fontSize: 11,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  void _showMessageActionMenu(BuildContext context, ServerMessage message) {
    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      builder: (context) => DesktopMessageActionMenu(
        message: message.text.decodeString,
        onCopy: () async {
          MixpanelManager().track('Chat Message Copied', properties: {'message': message.text});
          await Clipboard.setData(ClipboardData(text: message.text.decodeString));
          if (context.mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              SnackBar(
                content: const Text('✨ Message copied to clipboard'),
                backgroundColor: ResponsiveHelper.purplePrimary,
                behavior: SnackBarBehavior.floating,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                duration: const Duration(milliseconds: 2000),
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
              SnackBar(
                content: const Text('You cannot report your own messages'),
                backgroundColor: Colors.orange,
                behavior: SnackBarBehavior.floating,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                duration: const Duration(milliseconds: 2000),
              ),
            );
            return;
          }
          showDialog(
            context: context,
            builder: (context) {
              return getDialog(
                context,
                () => Navigator.of(context).pop(),
                () {
                  MixpanelManager().track('Chat Message Reported', properties: {'message': message.text});
                  Navigator.of(context).pop();
                  Navigator.of(context).pop();
                  context.read<MessageProvider>().removeLocalMessage(message.id);
                  reportMessageServer(message.id);
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: const Text('✅ Message reported successfully'),
                      backgroundColor: ResponsiveHelper.purplePrimary,
                      behavior: SnackBarBehavior.floating,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      duration: const Duration(milliseconds: 2000),
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
  }

  void _sendMessageUtil(String text) {
    var provider = context.read<MessageProvider>();
    provider.setSendingMessage(true);
    provider.addMessageLocally(text);
    scrollToBottom();
    textController.clear();
    provider.sendMessageStreamToServer(text);
    provider.clearSelectedFiles();
    provider.setSendingMessage(false);
  }

  void scrollToBottom() {
    SchedulerBinding.instance.addPostFrameCallback((_) {
      if (scrollController.hasClients) {
        scrollController.jumpTo(
          scrollController.position.maxScrollExtent,
        );
      }
    });
  }

  void _showAppSelectionSheet(BuildContext context, AppProvider appProvider) {
    final selectedApp = appProvider.selectedChatAppId.isEmpty || appProvider.selectedChatAppId == 'no_selected'
        ? null
        : appProvider.getSelectedApp();
    final availableApps = appProvider.apps.where((app) => app.worksWithChat() && app.enabled).toList();

    showModalBottomSheet(
      context: context,
      backgroundColor: Colors.transparent,
      isScrollControlled: true,
      builder: (context) => Container(
        height: MediaQuery.of(context).size.height * 0.7,
        decoration: BoxDecoration(
          color: ResponsiveHelper.backgroundSecondary,
          borderRadius: const BorderRadius.vertical(
            top: Radius.circular(20),
          ),
          border: Border.all(
            color: ResponsiveHelper.backgroundTertiary,
            width: 1,
          ),
        ),
        child: Column(
          children: [
            // Handle bar
            Container(
              margin: const EdgeInsets.only(top: 8),
              width: 40,
              height: 4,
              decoration: BoxDecoration(
                color: ResponsiveHelper.textQuaternary,
                borderRadius: BorderRadius.circular(2),
              ),
            ),

            // Header
            Padding(
              padding: const EdgeInsets.all(20),
              child: Row(
                children: [
                  const OmiSectionHeader(icon: FontAwesomeIcons.robot, title: 'Select Chat Assistant'),
                  const Spacer(),
                  OmiIconButton(
                    icon: FontAwesomeIcons.xmark,
                    style: OmiIconButtonStyle.outline,
                    borderOpacity: 0.1,
                    size: 28,
                    iconSize: 12,
                    borderRadius: 8,
                    onPressed: () => Navigator.pop(context),
                  ),
                ],
              ),
            ),

            // Apps list
            Expanded(
              child: ListView(
                padding: const EdgeInsets.symmetric(horizontal: 20),
                children: [
                  // Default Omi option
                  _buildAppSelectionItem(
                    app: null,
                    isSelected: selectedApp == null,
                    onTap: () => _handleAppSelection(context, appProvider, null),
                  ),

                  const SizedBox(height: 8),

                  // Available chat apps
                  ...availableApps.map((app) => _buildAppSelectionItem(
                        app: app,
                        isSelected: selectedApp?.id == app.id,
                        onTap: () => _handleAppSelection(context, appProvider, app),
                      )),

                  const SizedBox(height: 16),

                  // Enable more apps option
                  Container(
                    margin: const EdgeInsets.only(bottom: 8),
                    child: Material(
                      color: Colors.transparent,
                      child: InkWell(
                        onTap: () {
                          Navigator.pop(context);
                          final homeProvider = context.read<HomeProvider>();
                          homeProvider.setIndex(4);
                          homeProvider.onSelectedIndexChanged?.call(4);
                        },
                        borderRadius: BorderRadius.circular(12),
                        child: Container(
                          padding: const EdgeInsets.all(16),
                          decoration: BoxDecoration(
                            color: ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(
                              color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                              width: 1,
                            ),
                          ),
                          child: const Row(
                            children: [
                              Icon(
                                FontAwesomeIcons.store,
                                color: ResponsiveHelper.purplePrimary,
                                size: 16,
                              ),
                              SizedBox(width: 12),
                              Text(
                                'Enable More Apps',
                                style: TextStyle(
                                  color: ResponsiveHelper.textPrimary,
                                  fontSize: 14,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                              Spacer(),
                              Icon(
                                FontAwesomeIcons.chevronRight,
                                color: ResponsiveHelper.textTertiary,
                                size: 12,
                              ),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),

                  const SizedBox(height: 20),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAppSelectionItem({
    required App? app,
    required bool isSelected,
    required VoidCallback onTap,
  }) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(12),
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: isSelected
                  ? ResponsiveHelper.purplePrimary.withOpacity(0.15)
                  : ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: isSelected
                    ? ResponsiveHelper.purplePrimary.withOpacity(0.3)
                    : ResponsiveHelper.backgroundQuaternary.withOpacity(0.3),
                width: 1,
              ),
            ),
            child: Row(
              children: [
                // App avatar
                app != null
                    ? OmiAvatar(
                        size: 40,
                        imageUrl: app.getImageUrl(),
                      )
                    : OmiAvatar(
                        size: 40,
                        fallback: Image.asset(Assets.images.logoTransparent.path),
                      ),

                const SizedBox(width: 16),

                // App details
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        app?.name ?? 'Omi',
                        style: const TextStyle(
                          color: ResponsiveHelper.textPrimary,
                          fontSize: 16,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        app?.description ?? 'Default AI Assistant',
                        style: const TextStyle(
                          color: ResponsiveHelper.textSecondary,
                          fontSize: 12,
                        ),
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ],
                  ),
                ),

                const SizedBox(width: 12),

                // Selection indicator
                if (isSelected)
                  const Icon(
                    FontAwesomeIcons.check,
                    color: ResponsiveHelper.purplePrimary,
                    size: 16,
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  void _handleAppSelection(BuildContext context, AppProvider appProvider, App? app) async {
    Navigator.pop(context);

    final String selectedAppId = app?.id ?? 'no_selected';
    final String currentAppId = appProvider.selectedChatAppId.isEmpty ? 'no_selected' : appProvider.selectedChatAppId;

    if (selectedAppId != currentAppId) {
      appProvider.setSelectedChatAppId(app?.id);

      final messageProvider = context.read<MessageProvider>();
      await messageProvider.refreshMessages(dropdownSelected: true);

      if (messageProvider.messages.isEmpty) {
        messageProvider.sendInitialAppMessage(app);
      }

      scrollToBottom();
    }
  }

  void _showClearChatDialog(BuildContext context) {
    showDialog(
      context: context,
      builder: (context) => getDialog(
        context,
        () => Navigator.of(context).pop(),
        () {
          context.read<MessageProvider>().clearChat();
          Navigator.of(context).pop();
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: const Text('Chat cleared'),
              backgroundColor: ResponsiveHelper.backgroundTertiary,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              duration: const Duration(seconds: 2),
            ),
          );
        },
        'Clear Chat?',
        'Are you sure you want to clear the chat? This action cannot be undone.',
      ),
    );
  }
}
