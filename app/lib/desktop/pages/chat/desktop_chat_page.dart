import 'dart:io';
import 'dart:math' as math;

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
import 'package:omi/desktop/pages/chat/widgets/desktop_voice_recorder_widget.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/utils/analytics/mixpanel.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:provider/provider.dart';
import 'package:share_plus/share_plus.dart';

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

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    apps = prefs.appsList;
    scrollController = ScrollController();

    // Initialize animations for modern feel
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

    // Mark animations as initialized
    _animationsInitialized = true;

    SchedulerBinding.instance.addPostFrameCallback((_) async {
      var provider = context.read<MessageProvider>();
      if (provider.messages.isEmpty) {
        provider.refreshMessages();
      }

      // Start animations
      _fadeController.forward();
      _slideController.forward();

      scrollToBottom();
    });
    super.initState();
  }

  @override
  void dispose() {
    textController.dispose();
    scrollController.dispose();
    _fadeController.dispose();
    _slideController.dispose();
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);

    return Consumer2<MessageProvider, ConnectivityProvider>(
      builder: (context, provider, connectivityProvider, child) {
        return Container(
          decoration: BoxDecoration(
            gradient: LinearGradient(
              begin: Alignment.topCenter,
              end: Alignment.bottomCenter,
              colors: [
                ResponsiveHelper.backgroundPrimary,
                ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
              ],
            ),
            borderRadius: BorderRadius.circular(20),
          ),
          child: ClipRRect(
            borderRadius: BorderRadius.circular(20),
            child: Stack(
              children: [
                // Animated background pattern
                _buildAnimatedBackground(),

                // Main content with glassmorphism
                Container(
                  decoration: BoxDecoration(
                    color: Colors.white.withOpacity(0.02),
                    borderRadius: BorderRadius.circular(20),
                  ),
                  child: Column(
                    children: [
                      // Modern loading indicator
                      if (provider.isLoadingMessages) _buildModernLoadingBar(),

                      // Main chat area with enhanced styling
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

                      // Floating input area with glassmorphism
                      _buildFloatingInputArea(provider, connectivityProvider),
                    ],
                  ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildAnimatedBackground() {
    if (!_animationsInitialized) {
      return Container(
        decoration: BoxDecoration(
          gradient: RadialGradient(
            center: Alignment.topRight,
            radius: 2.0,
            colors: [
              ResponsiveHelper.purplePrimary.withOpacity(0.05),
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
                ResponsiveHelper.purplePrimary.withOpacity(0.05 + _pulseAnimation.value * 0.03),
                Colors.transparent,
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildModernLoadingBar() {
    return Container(
      height: 3,
      margin: const EdgeInsets.only(bottom: 8),
      decoration: BoxDecoration(
        borderRadius: const BorderRadius.only(
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
                  ResponsiveHelper.purplePrimary.withOpacity(0.3),
                  ResponsiveHelper.purplePrimary,
                  ResponsiveHelper.purplePrimary.withOpacity(0.3),
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
      return _buildModernLoadingState(provider.firstTimeLoadingText);
    }

    if (provider.isClearingChat) {
      return _buildModernLoadingState("Deleting your messages from Omi's memory...");
    }

    if (provider.messages.isEmpty) {
      return _buildModernEmptyState(connectivityProvider.isConnected);
    }

    return _buildMessagesList(provider);
  }

  Widget _buildModernLoadingState(String text) {
    Widget content = Column(
      mainAxisAlignment: MainAxisAlignment.center,
      children: [
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: ResponsiveHelper.backgroundSecondary.withOpacity(0.8),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: Colors.white.withOpacity(0.1),
              width: 1,
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.1),
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
                                  ResponsiveHelper.purplePrimary.withOpacity(0.7),
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
                            ResponsiveHelper.purplePrimary.withOpacity(0.7),
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
                style: TextStyle(
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

  Widget _buildModernEmptyState(bool isConnected) {
    Widget content = Container(
      padding: const EdgeInsets.all(40),
      margin: const EdgeInsets.all(32),
      decoration: BoxDecoration(
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: [
            ResponsiveHelper.backgroundSecondary.withOpacity(0.6),
            ResponsiveHelper.backgroundTertiary.withOpacity(0.4),
          ],
        ),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(
          color: Colors.white.withOpacity(0.1),
          width: 1,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.1),
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
                              ResponsiveHelper.purplePrimary.withOpacity(0.2),
                              ResponsiveHelper.purplePrimary.withOpacity(0.1),
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
                        ResponsiveHelper.purplePrimary.withOpacity(0.2),
                        ResponsiveHelper.purplePrimary.withOpacity(0.1),
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
            style: TextStyle(
              color: ResponsiveHelper.textPrimary,
              fontSize: 20,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            isConnected ? 'Start a conversation and let the magic begin' : 'Please check your internet connection',
            textAlign: TextAlign.center,
            style: TextStyle(
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
      reverse: true,
      controller: scrollController,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      itemCount: provider.messages.length,
      itemBuilder: (context, chatIndex) {
        final message = provider.messages[chatIndex];
        double topPadding = chatIndex == provider.messages.length - 1 ? 16 : 8;
        if (chatIndex != 0) message.askForNps = false;

        double bottomPadding = chatIndex == 0 ? 140 : 0;

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
    return Align(
      alignment: message.sender == MessageSender.ai ? Alignment.centerLeft : Alignment.centerRight,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.of(context).size.width * 0.7 * 0.7, // 70% of available chat width
        ),
        child: message.sender == MessageSender.ai
            ? Container(
                decoration: BoxDecoration(
                  color: const Color.fromARGB(255, 255, 255, 255).withOpacity(0.05),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(
                    color: ResponsiveHelper.backgroundTertiary.withOpacity(0.3),
                    width: 1,
                  ),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.05),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                padding: const EdgeInsets.all(16),
                child: AIMessage(
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
                ),
              )
            : Container(
                decoration: BoxDecoration(
                  color: ResponsiveHelper.purplePrimary.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(16),
                  boxShadow: [
                    BoxShadow(
                      color: Colors.black.withOpacity(0.05),
                      blurRadius: 8,
                      offset: const Offset(0, 2),
                    ),
                  ],
                ),
                padding: const EdgeInsets.all(16),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Text(
                      formatChatTimestamp(message.createdAt),
                      style: TextStyle(
                        color: ResponsiveHelper.textTertiary,
                        fontSize: 12,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      message.text.decodeString,
                      style: TextStyle(
                        color: ResponsiveHelper.textPrimary,
                        fontSize: 15,
                        height: 1.4,
                      ),
                    ),
                  ],
                ),
              ),
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
        color: ResponsiveHelper.backgroundSecondary.withOpacity(0.95),
        borderRadius: BorderRadius.circular(24),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.1),
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
          Text(
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
                              color: ResponsiveHelper.purplePrimary.withOpacity(0.2),
                              borderRadius: BorderRadius.circular(12),
                            ),
                            child: Icon(
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
              color: isDisabled ? ResponsiveHelper.textQuaternary.withOpacity(0.1) : ResponsiveHelper.purplePrimary.withOpacity(0.15),
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
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 8),
      constraints: const BoxConstraints(maxHeight: 120),
      decoration: BoxDecoration(
        color: ResponsiveHelper.backgroundTertiary.withOpacity(0.8),
        borderRadius: BorderRadius.circular(16),
      ),
      child: TextField(
        controller: textController,
        maxLines: null,
        keyboardType: TextInputType.multiline,
        style: TextStyle(
          fontSize: 14,
          color: ResponsiveHelper.textPrimary,
          height: 1.4,
        ),
        decoration: InputDecoration(
          hintText: '💬 Type your message...',
          hintStyle: TextStyle(
            fontSize: 14,
            color: ResponsiveHelper.textTertiary,
          ),
          border: InputBorder.none,
          contentPadding: const EdgeInsets.symmetric(
            horizontal: 16,
            vertical: 12,
          ),
        ),
      ),
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
                      child: Icon(
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
                  child: Icon(
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
    bool canSend = textController.text.trim().isNotEmpty && !provider.isUploadingFiles && connectivityProvider.isConnected;

    return Container(
      margin: const EdgeInsets.only(left: 8),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: canSend
              ? () {
                  String message = textController.text.trim();
                  if (message.isEmpty) return;
                  _sendMessageUtil(message);
                }
              : null,
          borderRadius: BorderRadius.circular(12),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 200),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: canSend ? ResponsiveHelper.purplePrimary : ResponsiveHelper.textQuaternary.withOpacity(0.3),
              borderRadius: BorderRadius.circular(12),
              boxShadow: canSend
                  ? [
                      BoxShadow(
                        color: ResponsiveHelper.purplePrimary.withOpacity(0.3),
                        blurRadius: 8,
                        offset: const Offset(0, 4),
                      ),
                    ]
                  : [],
            ),
            child: Icon(
              Icons.send_rounded,
              color: canSend ? Colors.white : ResponsiveHelper.textQuaternary,
              size: 18,
            ),
          ),
        ),
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
    final Size buttonSize = buttonBox.size;

    showMenu<String>(
      context: context,
      position: RelativeRect.fromLTRB(
        buttonPosition.dx, // Left edge aligned with button
        buttonPosition.dy - 220, // Position above the button (220px up to account for menu height)
        buttonPosition.dx + 200, // Right edge (200px wide menu)
        buttonPosition.dy, // Bottom edge at button top
      ),
      color: ResponsiveHelper.backgroundSecondary.withOpacity(0.95),
      elevation: 8,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(16),
      ),
      items: [
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
            title: "Select a Photo",
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
      if (result != null) {
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
                  style: TextStyle(
                    color: ResponsiveHelper.textPrimary,
                    fontSize: 14,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: TextStyle(
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
        scrollController.animateTo(
          0.0,
          duration: const Duration(milliseconds: 500),
          curve: Curves.easeOutCubic,
        );
      }
    });
  }
}
