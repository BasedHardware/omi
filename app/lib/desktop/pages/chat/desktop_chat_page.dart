import 'dart:ui';
import 'package:dotted_border/dotted_border.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/scheduler.dart';
import 'package:flutter/services.dart';
import 'dart:io';

import 'package:desktop_drop/desktop_drop.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:pasteboard/pasteboard.dart';
import 'package:path_provider/path_provider.dart';
import 'package:provider/provider.dart';
import 'package:omi/widgets/shimmer_with_timeout.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/desktop/pages/chat/widgets/desktop_voice_recorder_widget.dart';
import 'package:omi/gen/assets.gen.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/pages/chat/widgets/markdown_message_widget.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/ui/atoms/omi_avatar.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/ui/atoms/omi_icon_button.dart';
import 'package:omi/ui/atoms/omi_message_input.dart';
import 'package:omi/ui/atoms/omi_send_button.dart';
import 'package:omi/ui/atoms/omi_typing_indicator.dart';
import 'package:omi/ui/molecules/omi_chat_bubble.dart';
import 'package:omi/ui/molecules/omi_section_header.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_service.dart';
import 'package:omi/utils/responsive/responsive_helper.dart';
import 'package:omi/widgets/dialog.dart';
import 'package:omi/widgets/extensions/string.dart';

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
  bool _isDragging = false;

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

      if (event is KeyDownEvent &&
          event.logicalKey == LogicalKeyboardKey.keyV &&
          (HardwareKeyboard.instance.isMetaPressed || HardwareKeyboard.instance.isControlPressed)) {
        _handlePaste();
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
      provider.fetchChatApps();

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
        child: DropTarget(
          onDragEntered: (_) => setState(() => _isDragging = true),
          onDragExited: (_) => setState(() => _isDragging = false),
          onDragDone: (detail) {
            setState(() => _isDragging = false);
            List<File> files = detail.files.map((e) => File(e.path)).toList();
            context.read<MessageProvider>().addFiles(files);
          },
          child: Stack(
            children: [
              CallbackShortcuts(
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
              ),
              if (_isDragging)
                Positioned.fill(
                  child: ClipRRect(
                    borderRadius: BorderRadius.circular(20),
                    child: BackdropFilter(
                      filter: ImageFilter.blur(sigmaX: 5.0, sigmaY: 5.0),
                      child: Container(
                        color: Colors.black.withOpacity(0.6),
                        child: Center(
                          child: DottedBorder(
                            borderType: BorderType.RRect,
                            radius: const Radius.circular(20),
                            dashPattern: const [10, 5],
                            color: Colors.white.withOpacity(0.4),
                            strokeWidth: 2,
                            child: Container(
                              width: MediaQuery.of(context).size.width * 0.7,
                              height: MediaQuery.of(context).size.height * 0.7,
                              decoration: BoxDecoration(
                                color: Colors.transparent,
                                borderRadius: BorderRadius.circular(20),
                              ),
                              child: Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  Icon(
                                    Icons.file_upload_outlined,
                                    size: 64,
                                    color: Colors.white.withOpacity(0.8),
                                  ),
                                  const SizedBox(height: 16),
                                  Text(
                                    'Drop files here to add to your message',
                                    style: TextStyle(
                                      color: Colors.white.withOpacity(0.9),
                                      fontSize: 20,
                                      fontWeight: FontWeight.w500,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ),
                ),
            ],
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
                                context.l10n.chatWithAppName(selectedApp.name),
                                style: const TextStyle(
                                  color: ResponsiveHelper.textTertiary,
                                  fontSize: 11,
                                ),
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                              ),
                            ] else ...[
                              const SizedBox(height: 2),
                              Text(
                                context.l10n.defaultAiAssistant,
                                style: const TextStyle(
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
      return _buildLoadingState(context.l10n.deletingMessages);
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
          Builder(
            builder: (context) => Text(
              isConnected ? context.l10n.readyToChat : context.l10n.connectionNeeded,
              style: const TextStyle(
                color: ResponsiveHelper.textPrimary,
                fontSize: 20,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
          const SizedBox(height: 8),
          Builder(
            builder: (context) => Text(
              isConnected ? context.l10n.startConversation : context.l10n.checkInternetConnection,
              textAlign: TextAlign.center,
              style: const TextStyle(
                color: ResponsiveHelper.textSecondary,
                fontSize: 14,
                height: 1.5,
              ),
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
    return SelectionArea(
      child: ListView.builder(
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
            child: _buildModernMessageBubble(message, provider, chatIndex),
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
      ),
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
                    margin: const EdgeInsets.only(left: 4, top: 6),
                    child: Text(
                      formatChatTimestamp(message.createdAt, context: context),
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
                            const Icon(Icons.subdirectory_arrow_right, size: 14, color: ResponsiveHelper.textSecondary),
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
    var thinkingTextRaw = message.thinkings.isNotEmpty ? message.thinkings.last.decodeString : null;
    var thinkingText = thinkingTextRaw != null ? getThinkingDisplayText(thinkingTextRaw) : null;

    bool showTypingIndicator = provider.showTypingIndicator && chatIndex == provider.messages.length - 1;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisAlignment: MainAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        showTypingIndicator && message.text.isEmpty
            ? Container(
                margin: const EdgeInsets.only(top: 8),
                child: Row(
                  children: [
                    thinkingText != null
                        ? Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              mainAxisAlignment: MainAxisAlignment.start,
                              children: [
                                ShimmerWithTimeout(
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
        if (message.text.isNotEmpty && !showTypingIndicator)
          MessageActionBar(
            messageText: message.text.decodeString,
            setMessageNps: (int value, {String? reason}) {
              provider.setMessageNps(message, value, reason: reason);
            },
            currentNps: message.rating,
          ),
      ],
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
          Text(
            context.l10n.attachedFiles,
            style: const TextStyle(
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
          content: Text(context.l10n.maxFilesUploadError),
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
            child: Builder(
              builder: (context) => _buildPopupFileOption(
                context: context,
                icon: Icons.camera_alt_rounded,
                title: context.l10n.takePhoto,
                subtitle: context.l10n.captureWithCamera,
              ),
            ),
          ),
        PopupMenuItem<String>(
          value: 'gallery',
          padding: EdgeInsets.zero,
          child: Builder(
            builder: (context) => _buildPopupFileOption(
              context: context,
              icon: Icons.photo_library_rounded,
              title: context.l10n.selectImages,
              subtitle: context.l10n.chooseFromGallery,
            ),
          ),
        ),
        PopupMenuItem<String>(
          value: 'file',
          padding: EdgeInsets.zero,
          child: Builder(
            builder: (context) => _buildPopupFileOption(
              context: context,
              icon: Icons.attach_file_rounded,
              title: context.l10n.selectFile,
              subtitle: context.l10n.chooseAnyFileType,
            ),
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
    required BuildContext context,
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

  Future<void> _handlePaste() async {
    try {
      final files = await Pasteboard.files();
      if (files.isNotEmpty) {
        if (mounted) {
          context.read<MessageProvider>().addFiles(files.map((e) => File(e)).toList());
        }
        return;
      }

      final imageBytes = await Pasteboard.image;
      if (imageBytes != null) {
        final tempDir = await getTemporaryDirectory();
        final file = File('${tempDir.path}/pasted_image_${DateTime.now().millisecondsSinceEpoch}.png');
        await file.writeAsBytes(imageBytes);
        if (mounted) {
          context.read<MessageProvider>().addFiles([file]);
        }
      } else {
        final clipboardData = await Clipboard.getData(Clipboard.kTextPlain);
        final text = clipboardData?.text;
        if (text != null && text.isNotEmpty) {
          final selection = textController.selection;
          String newText;
          int newSelectionIndex;

          if (selection.isValid) {
            newText = textController.text.replaceRange(
              selection.start,
              selection.end,
              text,
            );
            newSelectionIndex = selection.start + text.length;
          } else {
            newText = textController.text + text;
            newSelectionIndex = newText.length;
          }

          textController.value = TextEditingValue(
            text: newText,
            selection: TextSelection.collapsed(offset: newSelectionIndex),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: const Text('Failed to paste content.'),
            backgroundColor: Colors.red,
            behavior: SnackBarBehavior.floating,
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
          ),
        );
      }
    }
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
                  Builder(
                    builder: (context) =>
                        OmiSectionHeader(icon: FontAwesomeIcons.robot, title: context.l10n.selectChatAssistant),
                  ),
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
              child: Consumer<MessageProvider>(
                builder: (context, messageProvider, child) {
                  final availableApps = messageProvider.chatApps;
                  return ListView(
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
                      if (availableApps.isEmpty && messageProvider.isLoadingChatApps)
                        const Center(
                          child: Padding(
                            padding: EdgeInsets.all(20.0),
                            child: CircularProgressIndicator(color: ResponsiveHelper.purplePrimary),
                          ),
                        )
                      else
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
                              child: Builder(
                                builder: (context) => Row(
                                  children: [
                                    const Icon(
                                      FontAwesomeIcons.store,
                                      color: ResponsiveHelper.purplePrimary,
                                      size: 16,
                                    ),
                                    const SizedBox(width: 12),
                                    Text(
                                      context.l10n.enableMoreApps,
                                      style: const TextStyle(
                                        color: ResponsiveHelper.textPrimary,
                                        fontSize: 14,
                                        fontWeight: FontWeight.w500,
                                      ),
                                    ),
                                    const Spacer(),
                                    const Icon(
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
                      ),

                      const SizedBox(height: 20),
                    ],
                  );
                },
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
                      Builder(
                        builder: (context) => Text(
                          app?.description ?? context.l10n.defaultAiAssistant,
                          style: const TextStyle(
                            color: ResponsiveHelper.textSecondary,
                            fontSize: 12,
                          ),
                          maxLines: 2,
                          overflow: TextOverflow.ellipsis,
                        ),
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
      builder: (dialogContext) => getDialog(
        dialogContext,
        () => Navigator.of(dialogContext).pop(),
        () {
          context.read<MessageProvider>().clearChat();
          Navigator.of(dialogContext).pop();
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(context.l10n.chatCleared),
              backgroundColor: ResponsiveHelper.backgroundTertiary,
              behavior: SnackBarBehavior.floating,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              duration: const Duration(seconds: 2),
            ),
          );
        },
        context.l10n.clearChatTitle,
        context.l10n.confirmClearChat,
      ),
    );
  }
}
