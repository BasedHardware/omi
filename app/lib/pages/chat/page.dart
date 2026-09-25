import 'dart:async';

import 'package:omi/utils/platform/platform_manager.dart';
import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter/scheduler.dart';

import 'package:collection/collection.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';
import 'package:pull_down_button/pull_down_button.dart';
import 'package:uuid/uuid.dart';
import 'package:visibility_detector/visibility_detector.dart';

import 'package:omi/backend/http/api/messages.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/app.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/message.dart';
import 'package:omi/pages/apps/widgets/capability_apps_page.dart';
import 'package:omi/pages/chat/chat_scroll_policy.dart';
import 'package:omi/pages/chat/widgets/ai_message.dart';
import 'package:omi/pages/chat/widgets/jump_to_latest_button.dart';
import 'package:omi/pages/settings/widgets/plans_sheet.dart';
import 'package:omi/pages/chat/widgets/user_message.dart';
import 'package:omi/pages/chat/widgets/voice_recorder_widget.dart';
import 'package:omi/pages/settings/integrations_page.dart';
import 'package:omi/providers/app_provider.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/integration_provider.dart';
import 'package:omi/providers/message_provider.dart';
import 'package:omi/providers/memories_provider.dart';
import 'package:omi/pages/chat/widgets/chat_starters.dart';
import 'package:omi/providers/usage_provider.dart';
import 'package:omi/providers/voice_recorder_provider.dart';
import 'package:omi/services/integrations/apple_health_service.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/pages/apps/widgets/app_actions.dart';
import 'package:omi/pages/chat/widgets/chat_apps_drawer.dart';
import 'package:omi/pages/chat/widgets/chat_composer_parts.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/widgets/bottom_nav_bar.dart';

class ChatPage extends StatefulWidget {
  final bool isPivotBottom;
  final String? autoMessage;
  final bool autoStartVoice;
  final ChatPageContext? initialChatContext;

  const ChatPage({
    super.key,
    this.isPivotBottom = false,
    this.autoMessage,
    this.autoStartVoice = false,
    this.initialChatContext,
  });

  @override
  State<ChatPage> createState() => ChatPageState();
}

class ChatPageState extends State<ChatPage> with AutomaticKeepAliveClientMixin, WidgetsBindingObserver {
  TextEditingController textController = TextEditingController();
  late ScrollController scrollController;
  late FocusNode textFieldFocusNode;

  bool _isInitialLoad = true;
  bool _hasInitialScrolled = false;
  double _lastBottomInset = 0;
  MessageProvider? _messageProvider;

  ChatScrollMode _chatScrollMode = ChatScrollMode.followingBottom;
  final List<Timer> _pendingScrollTimers = [];
  final List<Timer> _ownedLifecycleTimers = [];
  bool _isProgrammaticScroll = false;
  int _lastObservedMessageCount = 0;
  String? _lastObservedMessageId;
  int _lastObservedTextLength = 0;
  int _lastObservedContentBlockCount = 0;

  var prefs = SharedPreferencesUtil();
  late List<App> apps;

  final scaffoldKey = GlobalKey<ScaffoldState>();

  String? _selectedContext;
  bool _quotaSheetShown = false;
  ChatPageContext? _chatScope;

  @override
  bool get wantKeepAlive => true;

  @override
  void initState() {
    WidgetsBinding.instance.addObserver(this);
    apps = prefs.appsList;
    scrollController = ScrollController();
    textFieldFocusNode = FocusNode();
    textController.addListener(() {
      setState(() {});
    });
    textFieldFocusNode.addListener(() {
      setState(() {});
      if (textFieldFocusNode.hasFocus) {
        // Keep the live edge visible when the keyboard opens only if the reader is following.
        _scheduleModeAwareScroll(delayMs: 300, animated: true);
      }
    });

    SchedulerBinding.instance.addPostFrameCallback((_) async {
      var provider = context.read<MessageProvider>();
      _messageProvider = provider;
      // Listen for quota exceeded from any send path (text or voice)
      provider.addListener(_onMessageProviderChanged);
      if (provider.messages.isEmpty) {
        provider.refreshMessages();
      }
      // Fetch enabled chat apps
      provider.fetchChatApps();
      if (widget.initialChatContext != null) {
        setState(() => _chatScope = widget.initialChatContext);
      }
      // Sync Apple Health data if connected (ensures fresh data for health queries)
      _syncAppleHealthIfConnected();
      // Auto-start voice recording if requested (e.g., from home chat bar mic button)
      if (widget.autoStartVoice && _isInitialLoad) {
        _runLater(const Duration(milliseconds: 300), () {
          context.read<VoiceRecorderProvider>().startRecording();
        });
      } else if (_isInitialLoad) {
        // Auto-focus the text field only on initial load, not on app switches
        _runLater(const Duration(milliseconds: 300), () {
          final voiceRecorderProvider = context.read<VoiceRecorderProvider>();
          if (!voiceRecorderProvider.isActive && _isInitialLoad) {
            textFieldFocusNode.requestFocus();
          }
        });
      }
      // Handle auto-message from notification (e.g., daily reflection or goal advice)
      // This sends a message FROM Omi AI, not from the user
      if (widget.autoMessage != null && widget.autoMessage!.isNotEmpty && mounted) {
        // Wait for messages to load first, then add auto-message
        _runLater(const Duration(milliseconds: 800), () {
          final aiMessage = ServerMessage(
            const Uuid().v4(),
            DateTime.now(),
            widget.autoMessage!,
            MessageSender.ai,
            MessageType.text,
            null,
            false,
            [],
            [],
            [],
            askForNps: false,
          );
          context.read<MessageProvider>().addMessage(aiMessage);
          // Scroll after the message is added and rendered only while following.
          _scheduleModeAwareScroll(delayMs: 100);
        });
      }
    });
    super.initState();
  }

  void _onMessageProviderChanged() {
    final provider = context.read<MessageProvider>();
    if (mounted && provider.isChatQuotaExceeded && !_quotaSheetShown) {
      _quotaSheetShown = true;
      _showPlansSheetOnQuotaExceeded();
    } else if (!provider.isChatQuotaExceeded) {
      _quotaSheetShown = false;
    }
  }

  /// The keyboard shrinks the viewport after the initial jump to the bottom,
  /// which leaves the transcript parked mid-way (the list keeps its pixel offset
  /// while maxScrollExtent grows). Re-pin to the live edge on every inset change
  /// while the reader is following, so opening chat always lands on the last
  /// message regardless of keyboard animation timing.
  @override
  void didChangeMetrics() {
    final view = View.of(context);
    final bottomInset = view.viewInsets.bottom / view.devicePixelRatio;
    if ((bottomInset - _lastBottomInset).abs() < 1) return;
    _lastBottomInset = bottomInset;
    if (_chatScrollMode != ChatScrollMode.followingBottom) return;
    _schedulePostFrameModeAwareScroll();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _messageProvider?.removeListener(_onMessageProviderChanged);
    _cancelOwnedLifecycleTimers();
    _cancelPendingScrolls();
    textController.dispose();
    scrollController.dispose();
    textFieldFocusNode.dispose();
    super.dispose();
  }

  void _runLater(Duration delay, VoidCallback callback) {
    late final Timer timer;
    timer = Timer(delay, () {
      _ownedLifecycleTimers.remove(timer);
      if (!mounted) return;
      callback();
    });
    _ownedLifecycleTimers.add(timer);
  }

  void _cancelOwnedLifecycleTimers() {
    for (final timer in _ownedLifecycleTimers) {
      timer.cancel();
    }
    _ownedLifecycleTimers.clear();
  }

  void _syncAppleHealthIfConnected() async {
    final appleHealthService = AppleHealthService();
    if (appleHealthService.isAvailable) {
      final integrationProvider = context.read<IntegrationProvider>();
      await integrationProvider.ensureLoaded();
      if (!mounted) return;
      if (integrationProvider.isAppConnected(IntegrationApp.appleHealth)) {
        debugPrint('🍎 [Apple Health] Starting auto-sync on chat open…');
        final success = await appleHealthService.syncHealthDataToBackend(days: 7);
        debugPrint('🍎 [Apple Health] Auto-sync ${success ? "completed" : "failed"}');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);

    return Consumer2<MessageProvider, ConnectivityProvider>(
      builder: (context, provider, connectivityProvider, child) {
        _observeMessagesForAutoScroll(provider);
        return Scaffold(
          key: scaffoldKey,
          appBar: _buildAppBar(context, provider),
          endDrawer: ChatAppsDrawer(
            onSelectApp: (id) => _handleAppSelection(id, context.read<AppProvider>()),
            onEnableApps: _navigateToChatAppsPage,
            onDisableApp: _disableChatApp,
            onClearChat: _showClearChatDialog,
          ),
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
                      ? OmiLoadingState(label: provider.firstTimeLoadingText)
                      : provider.isClearingChat
                          ? OmiLoadingState(label: context.l10n.deletingMessages)
                          : (provider.messages.isEmpty)
                              ? ChatStarters(
                                  isConnected: connectivityProvider.isConnected,
                                  hasExistingData: _chatScope != null ||
                                      (context.watch<ConversationProvider?>()?.conversations.isNotEmpty ?? false) ||
                                      (context.watch<MemoriesProvider?>()?.memories.isNotEmpty ?? false) ||
                                      SharedPreferencesUtil().cachedMemories.isNotEmpty ||
                                      SharedPreferencesUtil().pendingMemories.isNotEmpty,
                                  onSelected: (prompt) {
                                    textController.text = prompt;
                                    textController.selection = TextSelection.collapsed(offset: prompt.length);
                                    textFieldFocusNode.requestFocus();
                                    OmiHaptics.selection();
                                  },
                                )
                              : LayoutBuilder(
                                  builder: (context, constraints) {
                                    return Theme(
                                      data: Theme.of(context).copyWith(
                                        textSelectionTheme: TextSelectionThemeData(
                                          selectionColor: Colors.white.withValues(alpha: 0.3),
                                          selectionHandleColor: OmiColors.accent,
                                        ),
                                      ),
                                      // Tight width: under the Column's loose constraints this Stack
                                      // otherwise shrink-wraps to its only non-positioned child (the
                                      // jump-to-latest chip, ~100pt), and every message collapses to a
                                      // character-wide column whenever that chip is visible.
                                      child: SizedBox(
                                        width: constraints.maxWidth,
                                        child: Stack(
                                          alignment: Alignment.bottomCenter,
                                          children: [
                                            Positioned.fill(
                                              child: NotificationListener<ScrollNotification>(
                                                onNotification: _handleScrollNotification,
                                                child: ListView.builder(
                                                  shrinkWrap: false,
                                                  reverse: false,
                                                  controller: scrollController,
                                                  padding: const EdgeInsets.fromLTRB(
                                                    18,
                                                    16,
                                                    18,
                                                    ChatScrollPolicy.transcriptBottomPadding,
                                                  ),
                                                  itemCount: provider.messages.length,
                                                  itemBuilder: (context, chatIndex) {
                                                    if (!_hasInitialScrolled && provider.messages.isNotEmpty) {
                                                      _hasInitialScrolled = true;
                                                      _schedulePostFrameModeAwareScroll();
                                                    }

                                                    final message = provider.messages[chatIndex];
                                                    double topPadding =
                                                        chatIndex == provider.messages.length - 1 ? 8 : 16;
                                                    double bottomPadding = chatIndex == 0 ? 16 : 0;

                                                    final messageBody = message.sender == MessageSender.ai
                                                        ? AIMessage(
                                                            showTypingIndicator: provider.showTypingIndicator &&
                                                                chatIndex == provider.messages.length - 1,
                                                            showThinkingAfterText: provider.agentThinkingAfterText,
                                                            message: message,
                                                            sendMessage: _sendMessageUtil,
                                                            onAskOmi: (text) {
                                                              setState(() {
                                                                _selectedContext = text;
                                                              });
                                                              textFieldFocusNode.requestFocus();
                                                            },
                                                            displayOptions: provider.messages.length <= 1,
                                                            appSender: provider.messageSenderApp(message.appId),
                                                            updateConversation: (ServerConversation conversation) {
                                                              context.read<ConversationProvider>().updateConversation(
                                                                    conversation,
                                                                  );
                                                            },
                                                            setMessageNps: (int value, {String? reason}) =>
                                                                provider.setMessageNps(message, value, reason: reason),
                                                            replyFailed: provider.isReplyFailed(message),
                                                            onRetry: provider.canRetryReply(message)
                                                                ? () => _retryReply(message)
                                                                : null,
                                                          )
                                                        : HumanMessage(
                                                            message: message,
                                                            onAskOmi: (text) {
                                                              setState(() {
                                                                _selectedContext = text;
                                                              });
                                                              textFieldFocusNode.requestFocus();
                                                            },
                                                          );
                                                    return VisibilityDetector(
                                                      key: ValueKey('chat-result-visibility-${message.id}'),
                                                      onVisibilityChanged: (info) {
                                                        if (message.sender == MessageSender.ai &&
                                                            !message.isEmpty &&
                                                            info.visibleFraction > 0 &&
                                                            context.mounted) {
                                                          provider.markChatResultVisible(message.id);
                                                        }
                                                      },
                                                      child: Padding(
                                                        key: ValueKey(message.id),
                                                        padding:
                                                            EdgeInsets.only(bottom: bottomPadding, top: topPadding),
                                                        child: messageBody,
                                                      ),
                                                    );
                                                  },
                                                ),
                                              ),
                                            ),
                                            if (_chatScrollMode == ChatScrollMode.freeScrolling)
                                              _buildJumpToLatestButton(),
                                          ],
                                        ),
                                      ),
                                    );
                                  },
                                ),
                ),
                // Send message area
                Container(
                  margin: const EdgeInsets.only(top: 10),
                  decoration: const BoxDecoration(
                    color: Colors.transparent,
                    borderRadius: BorderRadius.only(topLeft: Radius.circular(22), topRight: Radius.circular(22)),
                  ),
                  child: Consumer2<HomeProvider, VoiceRecorderProvider>(
                    builder: (context, home, voiceRecorderProvider, child) {
                      bool shouldShowSendButton(MessageProvider p) {
                        return !p.sendingMessage && !voiceRecorderProvider.isActive;
                      }

                      bool shouldShowVoiceRecorderButton() {
                        return !voiceRecorderProvider.isActive;
                      }

                      bool shouldShowMenuButton() {
                        return !voiceRecorderProvider.isActive;
                      }

                      return Column(
                        children: [
                          // Selected images display above the send bar
                          const ChatSelectedFilesStrip(),
                          if (!connectivityProvider.isConnected) const _OfflineHint(),
                          // Scope chip (#4515) — clears an active conversation scope (Ask about this)
                          Builder(
                            builder: (context) {
                              final scope = _chatScope;
                              final hasConversation = scope?.type == 'conversation' && (scope?.id?.isNotEmpty ?? false);
                              if (!hasConversation) return const SizedBox.shrink();
                              final l10n = context.l10n;
                              return Padding(
                                padding: const EdgeInsets.fromLTRB(16, 4, 16, 0),
                                child: SingleChildScrollView(
                                  scrollDirection: Axis.horizontal,
                                  child: Row(
                                    children: [
                                      _ComposerChip(
                                        label: l10n.chatScopeAbout(scope!.title ?? l10n.conversationTab),
                                        onRemove: () => setState(() => _chatScope = null),
                                      ),
                                    ],
                                  ),
                                ),
                              );
                            },
                          ),
                          // Send bar
                          SafeArea(
                            bottom: false,
                            maintainBottomViewPadding: false,
                            child: Padding(
                              padding: EdgeInsets.only(
                                left: 8,
                                right: 8,
                                top: provider.selectedFiles.isNotEmpty ? 0 : 8,
                                bottom: widget.isPivotBottom
                                    ? 6
                                    : (textFieldFocusNode.hasFocus &&
                                            (textController.text.length > 40 || textController.text.contains('\n'))
                                        ? 4
                                        : 10),
                              ),
                              child: Stack(
                                clipBehavior: Clip.none,
                                children: [
                                  Row(
                                    crossAxisAlignment: CrossAxisAlignment.center,
                                    children: [
                                      // Placeholder for the floating LEFT button so the pill
                                      // sits at the right x-position. The actual button is
                                      // rendered as a Positioned overlay below so the pill's
                                      // shadow can't bleed onto it.
                                      if ((voiceRecorderProvider.isActive &&
                                              voiceRecorderProvider.state == VoiceRecorderState.recording) ||
                                          (!voiceRecorderProvider.isActive && shouldShowMenuButton()))
                                        const SizedBox(width: 56),
                                      // CENTER pill — text field/waveform + right-side button stays inside.
                                      Expanded(
                                        child: Container(
                                          // 4 + 44 pt target + 4 keeps the pill as tall as the 38 pt button did.
                                          padding: const EdgeInsets.only(left: 14, right: 4, top: 4, bottom: 4),
                                          decoration: BoxDecoration(
                                            color: OmiColors.surface1,
                                            borderRadius: OmiRadius.pillAll,
                                            border: Border.all(color: OmiColors.surface3, width: 1),
                                            boxShadow: kChatComposerShadow,
                                          ),
                                          child: Row(
                                            crossAxisAlignment: CrossAxisAlignment.center,
                                            children: [
                                              Expanded(
                                                child: Column(
                                                  mainAxisSize: MainAxisSize.min,
                                                  crossAxisAlignment: CrossAxisAlignment.start,
                                                  children: [
                                                    if (_selectedContext != null && !voiceRecorderProvider.isActive)
                                                      _SelectedTextChip(
                                                        text: _selectedContext!,
                                                        onRemove: () => setState(() => _selectedContext = null),
                                                      ),
                                                    voiceRecorderProvider.isActive
                                                        ? VoiceRecorderWidget(
                                                            onTranscriptReady: (transcript, autoSend) {
                                                              textController.text = transcript;
                                                              voiceRecorderProvider.close();
                                                              context
                                                                  .read<MessageProvider>()
                                                                  .setNextMessageOriginIsVoice(true);
                                                              if (autoSend && transcript.trim().isNotEmpty) {
                                                                _sendMessageUtil(transcript.trim());
                                                              }
                                                            },
                                                            onClose: () {
                                                              voiceRecorderProvider.close();
                                                            },
                                                          )
                                                        : Theme(
                                                            data: Theme.of(context).copyWith(
                                                              textSelectionTheme: TextSelectionThemeData(
                                                                selectionColor: Colors.grey.withValues(alpha: 0.4),
                                                                selectionHandleColor: Colors.white,
                                                              ),
                                                            ),
                                                            child: TextField(
                                                              key: const ValueKey('omi.chat.input'),
                                                              enabled: true,
                                                              controller: textController,
                                                              focusNode: textFieldFocusNode,
                                                              obscureText: false,
                                                              textAlign: TextAlign.start,
                                                              // y: -0.35 nudges glyphs up. Font line metrics
                                                              // place the visual baseline below the line box
                                                              // center, so plain `.center` reads slightly low.
                                                              textAlignVertical: const TextAlignVertical(y: -0.35),
                                                              decoration: InputDecoration(
                                                                hintText: context.l10n.askAnything,
                                                                hintStyle: OmiType.callout.copyWith(
                                                                  color: OmiColors.textTertiary,
                                                                ),
                                                                focusedBorder: InputBorder.none,
                                                                enabledBorder: InputBorder.none,
                                                                contentPadding: const EdgeInsets.symmetric(
                                                                  horizontal: 4,
                                                                  vertical: 10,
                                                                ),
                                                                isDense: true,
                                                              ),
                                                              minLines: 1,
                                                              maxLines: 10,
                                                              keyboardType: TextInputType.multiline,
                                                              textCapitalization: TextCapitalization.sentences,
                                                              style: OmiType.callout.copyWith(height: 1.2),
                                                            ),
                                                          ),
                                                  ],
                                                ),
                                              ),
                                              const SizedBox(width: 8),
                                              // Right-side button — stays INSIDE the pill.
                                              // Send button while recording — transcribes and sends in one tap.
                                              if (voiceRecorderProvider.isActive)
                                                ChatComposerRoundButton(
                                                  icon: const FaIcon(FontAwesomeIcons.arrowUp),
                                                  label: context.l10n.chatSendMessage,
                                                  onPressed: voiceRecorderProvider.state == VoiceRecorderState.recording
                                                      ? () {
                                                          OmiHaptics.medium();
                                                          voiceRecorderProvider.requestAutoSendOnNextTranscript();
                                                          voiceRecorderProvider.processRecording();
                                                        }
                                                      : null,
                                                ),
                                              // Microphone button — round white pill matching the send button.
                                              if (!voiceRecorderProvider.isActive &&
                                                  shouldShowVoiceRecorderButton() &&
                                                  textController.text.isEmpty)
                                                ChatComposerRoundButton(
                                                  icon: const FaIcon(FontAwesomeIcons.microphone),
                                                  label: context.l10n.startVoiceRecording,
                                                  onPressed: () {
                                                    OmiHaptics.light();
                                                    FocusScope.of(context).unfocus();
                                                    voiceRecorderProvider.startRecording();
                                                  },
                                                ),
                                              // Send button — only when there's text and not in voice mode.
                                              // Offline or uploading it stays visible but is drawn disabled.
                                              if (!voiceRecorderProvider.isActive && shouldShowSendButton(provider))
                                                ValueListenableBuilder<TextEditingValue>(
                                                  valueListenable: textController,
                                                  builder: (context, value, child) {
                                                    bool hasText = value.text.trim().isNotEmpty;
                                                    if (!hasText) return const SizedBox.shrink();

                                                    bool canSend = hasText &&
                                                        !provider.sendingMessage &&
                                                        !provider.isUploadingFiles &&
                                                        connectivityProvider.isConnected;

                                                    return ChatComposerRoundButton(
                                                      buttonKey: const ValueKey('omi.chat.send'),
                                                      icon: const FaIcon(FontAwesomeIcons.arrowUp),
                                                      label: context.l10n.chatSendMessage,
                                                      onPressed: canSend
                                                          ? () {
                                                              OmiHaptics.medium();
                                                              String message = textController.text.trim();
                                                              if (message.isEmpty) return;
                                                              _sendMessageUtil(message);
                                                            }
                                                          : null,
                                                    );
                                                  },
                                                ),
                                            ],
                                          ),
                                        ),
                                      ),
                                    ],
                                  ),
                                  // LEFT button — Stop (recording) or Plus (idle). Rendered AFTER
                                  // the inner Row so it sits on top of the pill's shadow.
                                  if (voiceRecorderProvider.isActive &&
                                      voiceRecorderProvider.state == VoiceRecorderState.recording)
                                    Positioned(
                                      left: 0,
                                      top: 0,
                                      bottom: 0,
                                      child: Center(
                                        child: ChatComposerSideButton(
                                          icon: const Icon(Icons.stop),
                                          label: context.l10n.stopRecording,
                                          onPressed: () {
                                            OmiHaptics.light();
                                            voiceRecorderProvider.processRecording();
                                          },
                                        ),
                                      ),
                                    )
                                  else if (!voiceRecorderProvider.isActive && shouldShowMenuButton())
                                    Positioned(
                                      left: 0,
                                      top: 0,
                                      bottom: 0,
                                      child: Center(
                                        child: PullDownButton(
                                          itemBuilder: (context) => [
                                            PullDownMenuItem(
                                              title: context.l10n.takePhoto,
                                              iconWidget: const FaIcon(FontAwesomeIcons.camera, size: 16),
                                              onTap: () {
                                                OmiHaptics.selection();
                                                if (mounted) {
                                                  this.context.read<MessageProvider>().captureImage();
                                                }
                                              },
                                            ),
                                            PullDownMenuItem(
                                              title: context.l10n.photoLibrary,
                                              iconWidget: const FaIcon(FontAwesomeIcons.images, size: 16),
                                              onTap: () {
                                                OmiHaptics.selection();
                                                if (mounted) {
                                                  this.context.read<MessageProvider>().selectImage();
                                                }
                                              },
                                            ),
                                            PullDownMenuItem(
                                              title: context.l10n.chooseFile,
                                              iconWidget: const FaIcon(FontAwesomeIcons.folder, size: 16),
                                              onTap: () {
                                                OmiHaptics.selection();
                                                if (mounted) {
                                                  this.context.read<MessageProvider>().selectFile();
                                                }
                                              },
                                            ),
                                          ],
                                          position: PullDownMenuPosition.automatic,
                                          buttonBuilder: (context, showMenu) => ChatComposerSideButton(
                                            icon: const FaIcon(FontAwesomeIcons.plus),
                                            label: context.l10n.chatAddAttachment,
                                            onPressed: () async {
                                              OmiHaptics.light();
                                              if (provider.selectedFiles.length > 3) {
                                                OmiFeedback.info(context, context.l10n.maxFilesLimit);
                                                return;
                                              }
                                              if (textFieldFocusNode.hasFocus) {
                                                FocusScope.of(context).unfocus();
                                                await Future.delayed(const Duration(milliseconds: 280));
                                                if (!context.mounted) return;
                                              }
                                              showMenu();
                                            },
                                          ),
                                        ),
                                      ),
                                    ),
                                ],
                              ),
                            ),
                          ),
                        ],
                      );
                    },
                  ),
                ),
                if (!textFieldFocusNode.hasFocus)
                  BottomNavBar(
                    onTabTap: (index, isRepeat) {
                      context.read<HomeProvider>().setIndex(index);
                      Navigator.of(context).pop();
                    },
                  ),
              ],
            ),
          ),
        );
      },
    );
  }

  _sendMessageUtil(String text) async {
    var provider = context.read<MessageProvider>();
    // Guard against re-entry (rapid double-tap of send, voice→transcribeSuccess
    // race firing onTranscriptReady twice, etc.). Without this the chat could
    // submit the same text twice and the AI replies twice.
    if (provider.sendingMessage) return;
    String? currentContext = _selectedContext;
    setState(() {
      _selectedContext = null;
    });
    // Remove focus from text field
    FocusManager.instance.primaryFocus?.unfocus();
    if (currentContext != null) {
      text = 'Context: "$currentContext"\n\n$text';
    }

    provider.setSendingMessage(true);
    provider.addMessageLocally(text);
    textController.clear();

    _resumeFollowingAndScroll(delayMs: 300, animated: true);

    await provider.sendMessageStreamToServer(text, context: _chatScope);

    // Plans sheet is shown reactively via _onMessageProviderChanged listener

    provider.clearSelectedFiles();
    provider.setSendingMessage(false);
  }

  /// Sends the message behind a failed reply again (the reply's Try Again).
  Future<void> _retryReply(ServerMessage failed) async {
    final provider = context.read<MessageProvider>();
    if (provider.sendingMessage) return;
    provider.setSendingMessage(true);
    _resumeFollowingAndScroll(animated: true);
    await provider.retryFailedReply(failed);
  }

  void _showPlansSheetOnQuotaExceeded() {
    if (!mounted) return;
    // Refresh subscription data so the plans sheet is up-to-date
    context.read<UsageProvider>().fetchSubscription();
    showOmiSheet<void>(context: context, padding: EdgeInsets.zero, builder: (_) => const _PlansSheetWrapper());
  }

  sendInitialAppMessage(App? app) async {
    // The provider outlives this page: release the composer even if the page closes mid-request.
    final provider = context.read<MessageProvider>();
    provider.setSendingMessage(true);
    _resumeFollowingAndScroll();
    try {
      final message = await getInitialAppMessage(app?.id);
      if (!mounted) return;
      provider.addMessage(message);
      _resumeFollowingAndScroll();
    } finally {
      provider.setSendingMessage(false);
    }
  }

  void _observeMessagesForAutoScroll(MessageProvider provider) {
    final messages = provider.messages;
    final count = messages.length;
    final lastMessage = messages.isNotEmpty ? messages.last : null;
    final lastId = lastMessage?.id;
    final textLength = lastMessage?.text.length ?? 0;
    final thinkingCount = lastMessage?.thinkings.length ?? 0;

    final addedMessages = count > _lastObservedMessageCount;
    final lastMessageChanged = lastId != _lastObservedMessageId;
    final streamedTextChanged = lastId == _lastObservedMessageId && textLength != _lastObservedTextLength;
    final streamedBlocksChanged = lastId == _lastObservedMessageId && thinkingCount != _lastObservedContentBlockCount;

    _lastObservedMessageCount = count;
    _lastObservedMessageId = lastId;
    _lastObservedTextLength = textLength;
    _lastObservedContentBlockCount = thinkingCount;

    if (count == 0) return;

    if (addedMessages && !_hasInitialScrolled) {
      _hasInitialScrolled = true;
      _schedulePostFrameModeAwareScroll();
      return;
    }

    if (_chatScrollMode == ChatScrollMode.followingBottom &&
        (addedMessages || lastMessageChanged || streamedTextChanged || streamedBlocksChanged)) {
      _scheduleModeAwareScroll(delayMs: 0, animated: streamedTextChanged || streamedBlocksChanged);
    }
  }

  bool _handleScrollNotification(ScrollNotification notification) {
    if (notification.depth != 0) return false;

    final isUserScroll = notification is UserScrollNotification && notification.direction != ScrollDirection.idle;
    final isDragScroll = notification is ScrollUpdateNotification && notification.dragDetails != null;

    if (_isProgrammaticScroll && !isUserScroll && !isDragScroll) return false;

    final next = ChatScrollPolicy.nextMode(
      current: _chatScrollMode,
      isUserOrDragScroll: isUserScroll || isDragScroll,
      atLiveEdge: ChatScrollPolicy.atLiveEdge(notification.metrics),
    );
    if (next == null) return false;

    _chatScrollMode = next;
    _cancelPendingScrolls();
    if (mounted) setState(() {});
    return false;
  }

  Widget _buildJumpToLatestButton() {
    return ChatJumpToLatestButton(label: context.l10n.latest, onTap: () => _resumeFollowingAndScroll(animated: true));
  }

  void scrollToBottomOnSend() {
    _resumeFollowingAndScroll(animated: true);
  }

  void _resumeFollowingAndScroll({int delayMs = 0, bool animated = false}) {
    _cancelPendingScrolls();
    _chatScrollMode = ChatScrollMode.followingBottom;
    if (mounted) setState(() {});
    _scheduleModeAwareScroll(delayMs: delayMs, animated: animated, force: true);
  }

  void _schedulePostFrameModeAwareScroll({bool animated = false, bool force = false}) {
    SchedulerBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      _scheduleModeAwareScroll(delayMs: 0, animated: animated, force: force);
    });
  }

  void _scheduleModeAwareScroll({int delayMs = 50, bool animated = false, bool force = false}) {
    final timer = Timer(Duration(milliseconds: delayMs), () {
      _pendingScrollTimers.removeWhere((candidate) => !candidate.isActive);
      if (!mounted) return;
      _scrollToBottom(animated: animated, force: force);
    });
    _pendingScrollTimers.add(timer);
  }

  void _cancelPendingScrolls() {
    for (final timer in _pendingScrollTimers) {
      timer.cancel();
    }
    _pendingScrollTimers.clear();
  }

  void scrollToBottom({bool animated = false}) {
    _scrollToBottom(animated: animated);
  }

  void _scrollToBottom({bool animated = false, bool force = false}) {
    if (!scrollController.hasClients) return;
    if (!force && _chatScrollMode != ChatScrollMode.followingBottom) return;

    final position = scrollController.position;
    final target = position.maxScrollExtent;
    final distance = (target - position.pixels).abs();
    if (distance <= 20) return;

    _isProgrammaticScroll = true;

    if (distance > 350 || !animated) {
      scrollController.jumpTo(target);
      _isProgrammaticScroll = false;
      return;
    }

    scrollController
        .animateTo(target, duration: const Duration(milliseconds: 220), curve: Curves.easeOut)
        .whenComplete(() => _isProgrammaticScroll = false);
  }

  void _handleAppSelection(String? val, AppProvider provider) {
    if (val == null || val == provider.selectedChatAppId) {
      return;
    }

    // Unfocus the text field to prevent keyboard issues
    textFieldFocusNode.unfocus();

    // select app by id
    _selectApp(val, provider);
  }

  Future<void> _showClearChatDialog() async {
    if (!mounted) return;
    final l10n = context.l10n;
    // Clearing cannot be undone: confirm every time, with the verb on the button.
    final confirmed = await showOmiConfirm(
      context,
      title: l10n.clearChatQuestion,
      message: l10n.clearChatConfirm,
      confirmLabel: l10n.clearChat,
      destructive: true,
    );
    if (confirmed && mounted) context.read<MessageProvider>().clearChat();
  }

  Future<void> _navigateToChatAppsPage() async {
    if (!mounted) return;

    PlatformManager.instance.analytics.pageOpened('Chat Apps');
    // Navigate to chat capability apps page
    await routeToPage(
      context,
      CapabilityAppsPage(
        capability: AppCapability(id: 'chat', title: context.l10n.chatAssistantsTitle),
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
    messageProvider.setChatApps(localChatApps);
  }

  /// Disables a chat app everywhere, with Undo (the same action as Disable on its detail page).
  Future<void> _disableChatApp(App app) async {
    final messageProvider = context.read<MessageProvider>();
    Navigator.of(context).maybePop(); // close the drawer so the Undo toast is visible
    await disableAppWithUndo(
      context,
      app,
      onHidden: () => messageProvider.removeChatApp(app.id),
      onRestored: () {
        if (messageProvider.chatApps.every((a) => a.id != app.id)) {
          messageProvider.setChatApps(List.of(messageProvider.chatApps)..add(app));
        }
      },
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
    final l10n = context.l10n;
    return AppBar(
      elevation: 0,
      leading: const Center(child: OmiBackButton.circled()),
      title: Consumer<AppProvider>(
        builder: (context, appProvider, child) {
          final selectedApp = provider.chatApps.firstWhereOrNull((app) => app.id == appProvider.selectedChatAppId);
          return Row(
            mainAxisAlignment: MainAxisAlignment.center,
            mainAxisSize: MainAxisSize.min,
            children: [
              selectedApp != null ? ChatAppAvatar(app: selectedApp) : const ChatOmiAvatar(),
              const SizedBox(width: OmiSpacing.xs),
              ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 140),
                child: Text(
                  selectedApp != null ? selectedApp.getName() : l10n.omiAppName,
                  style: OmiType.callout,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          );
        },
      ),
      centerTitle: true,
      actions: [
        OmiIconButton.filled(
          icon: const Icon(Icons.extension),
          label: l10n.chatAppsTitle,
          onPressed: () {
            OmiHaptics.selection();
            // Dismiss the keyboard before opening the drawer, once the scaffold has settled.
            FocusScope.of(context).unfocus();
            WidgetsBinding.instance.addPostFrameCallback((_) => scaffoldKey.currentState?.openEndDrawer());
          },
        ),
        const SizedBox(width: OmiSpacing.xxs),
      ],
      bottom: provider.isLoadingMessages
          ? PreferredSize(
              preferredSize: const Size.fromHeight(32),
              child: Container(
                width: double.infinity,
                height: 32,
                color: OmiColors.surface2,
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const OmiSpinner(size: OmiSpinnerSize.small),
                    const SizedBox(width: OmiSpacing.xs),
                    Text(l10n.syncingMessages, style: OmiType.footnote.copyWith(color: OmiColors.textSecondary)),
                  ],
                ),
              ),
            )
          : null,
    );
  }
}

/// "You're offline" above the composer; Send is disabled until the connection returns.
class _OfflineHint extends StatelessWidget {
  const _OfflineHint();

  @override
  Widget build(BuildContext context) {
    return Semantics(
      liveRegion: true,
      child: Padding(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md, 0),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            const ExcludeSemantics(child: Icon(Icons.cloud_off_rounded, size: 14, color: OmiColors.textTertiary)),
            const SizedBox(width: 6),
            Flexible(
              child: Text(
                context.l10n.chatOfflineHint,
                style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
                textAlign: TextAlign.center,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

/// A small chip above or inside the composer with a remove control (the conversation scope).
class _ComposerChip extends StatelessWidget {
  const _ComposerChip({required this.label, required this.onRemove});

  final String label;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return Semantics(
      button: true,
      label: label,
      hint: MaterialLocalizations.of(context).deleteButtonTooltip,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: onRemove,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
          child: Center(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: 6),
              decoration: BoxDecoration(
                color: OmiColors.surface2,
                borderRadius: OmiRadius.lgAll,
                border: Border.all(color: OmiColors.textTertiary),
              ),
              child: ExcludeSemantics(
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Flexible(
                      child: Text(
                        label,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: OmiType.footnote.copyWith(fontWeight: FontWeight.w500),
                      ),
                    ),
                    const SizedBox(width: 6),
                    const Icon(Icons.close, size: 14, color: OmiColors.textSecondary),
                  ],
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}

/// The quoted text the next message asks about ("Ask Omi" on a selection), with a remove control.
class _SelectedTextChip extends StatelessWidget {
  const _SelectedTextChip({required this.text, required this.onRemove});

  final String text;
  final VoidCallback onRemove;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: OmiSpacing.xxs, left: 2),
      child: Container(
        decoration: const BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.lgAll),
        padding: const EdgeInsets.only(left: OmiSpacing.sm),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const ExcludeSemantics(
              child: Icon(Icons.subdirectory_arrow_right, size: 14, color: OmiColors.textSecondary),
            ),
            const SizedBox(width: OmiSpacing.xs),
            Flexible(
              child: Text(
                text,
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w500),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            OmiIconButton(
              icon: const Icon(Icons.close, size: 16),
              label: context.l10n.chatRemoveSelectedText,
              color: OmiColors.textSecondary,
              onPressed: onRemove,
            ),
          ],
        ),
      ),
    );
  }
}

class _PlansSheetWrapper extends StatefulWidget {
  const _PlansSheetWrapper();

  @override
  State<_PlansSheetWrapper> createState() => _PlansSheetWrapperState();
}

class _PlansSheetWrapperState extends State<_PlansSheetWrapper> with TickerProviderStateMixin {
  late AnimationController _waveController;
  late AnimationController _arrowController;
  late AnimationController _notesController;
  late Animation<double> _arrowAnimation;

  @override
  void initState() {
    super.initState();
    _waveController = AnimationController(vsync: this, duration: const Duration(seconds: 2))..repeat();
    _arrowController = AnimationController(vsync: this, duration: const Duration(milliseconds: 800))..repeat();
    _notesController = AnimationController(vsync: this, duration: const Duration(seconds: 3))..repeat();
    _arrowAnimation = Tween<double>(
      begin: 0,
      end: 10,
    ).animate(CurvedAnimation(parent: _arrowController, curve: Curves.easeInOut));
  }

  @override
  void dispose() {
    _waveController.dispose();
    _arrowController.dispose();
    _notesController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PlansSheet(
      waveController: _waveController,
      notesController: _notesController,
      arrowController: _arrowController,
      arrowAnimation: _arrowAnimation,
    );
  }
}
