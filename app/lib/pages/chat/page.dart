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

class ChatPage extends StatefulWidget {
  final bool isPivotBottom;
  final String? autoMessage;
  final String? initialDraft;
  final bool autoStartVoice;
  final ChatPageContext? initialChatContext;

  const ChatPage({
    super.key,
    this.isPivotBottom = false,
    this.autoMessage,
    this.initialDraft,
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
  bool _showLatestJump = false;
  Timer? _latestJumpIdleTimer;
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
    if (widget.initialDraft != null) textController.text = widget.initialDraft!;
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
    _latestJumpIdleTimer?.cancel();
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
        // Empty, the sheet is glass over the blurred page underneath (chat_route.dart); once there
        // is a transcript it turns solid so long answers stay readable.
        final isGlass = provider.messages.isEmpty && !provider.isLoadingMessages && !provider.isClearingChat;
        return AnimatedContainer(
          duration: const Duration(milliseconds: 260),
          curve: Curves.easeOut,
          color: isGlass ? Colors.transparent : OmiColors.surface0,
          child: Scaffold(
            key: scaffoldKey,
            backgroundColor: Colors.transparent,
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
                                : _buildTranscript(provider),
                  ),
                  _buildComposer(context, provider, connectivityProvider),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildTranscript(MessageProvider provider) {
    return LayoutBuilder(
      builder: (context, constraints) {
        return Theme(
          data: Theme.of(context).copyWith(
            textSelectionTheme: TextSelectionThemeData(
              selectionColor: OmiColors.textPrimary.withValues(alpha: 0.3),
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
                      padding: const EdgeInsets.fromLTRB(18, 16, 18, ChatScrollPolicy.transcriptBottomPadding),
                      itemCount: provider.messages.length,
                      itemBuilder: (context, chatIndex) {
                        if (!_hasInitialScrolled && provider.messages.isNotEmpty) {
                          _hasInitialScrolled = true;
                          _schedulePostFrameModeAwareScroll();
                        }

                        final message = provider.messages[chatIndex];
                        double topPadding = chatIndex == provider.messages.length - 1 ? 8 : 16;
                        double bottomPadding = chatIndex == 0 ? 16 : 0;

                        final messageBody = message.sender == MessageSender.ai
                            ? AIMessage(
                                showTypingIndicator:
                                    provider.showTypingIndicator && chatIndex == provider.messages.length - 1,
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
                                  context.read<ConversationProvider>().updateConversation(conversation);
                                },
                                setMessageNps: (int value, {String? reason}) =>
                                    provider.setMessageNps(message, value, reason: reason),
                                replyFailed: provider.isReplyFailed(message),
                                onRetry: provider.canRetryReply(message) ? () => _retryReply(message) : null,
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
                            padding: EdgeInsets.only(bottom: bottomPadding, top: topPadding),
                            child: messageBody,
                          ),
                        );
                      },
                    ),
                  ),
                ),
                if (_chatScrollMode == ChatScrollMode.freeScrolling && _showLatestJump) _buildJumpToLatestButton(),
              ],
            ),
          ),
        );
      },
    );
  }

  /// The composer card: the field (or the voice waveform) on top; attach, who answers, and the
  /// mic or send button underneath.
  Widget _buildComposer(BuildContext context, MessageProvider provider, ConnectivityProvider connectivityProvider) {
    return Consumer<VoiceRecorderProvider>(
      builder: (context, voiceRecorderProvider, child) {
        final voiceActive = voiceRecorderProvider.isActive;
        final recording = voiceRecorderProvider.state == VoiceRecorderState.recording;
        return Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            // Selected images display above the composer
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
            SafeArea(
              top: false,
              maintainBottomViewPadding: false,
              child: Container(
                margin: EdgeInsets.fromLTRB(10, provider.selectedFiles.isNotEmpty ? 0 : 8, 10, 10),
                padding: const EdgeInsets.fromLTRB(16, 8, 6, 4),
                decoration: BoxDecoration(
                  color: OmiColors.surface1,
                  borderRadius: const BorderRadius.all(Radius.circular(24)),
                  border: Border.all(color: OmiColors.border),
                  boxShadow: kChatComposerShadow,
                ),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (_selectedContext != null && !voiceActive)
                      _SelectedTextChip(
                        text: _selectedContext!,
                        onRemove: () => setState(() => _selectedContext = null),
                      ),
                    if (voiceActive)
                      Padding(
                        padding: const EdgeInsets.only(right: 10, top: 4),
                        child: VoiceRecorderWidget(
                          onTranscriptReady: (transcript, autoSend) {
                            textController.text = transcript;
                            voiceRecorderProvider.close();
                            context.read<MessageProvider>().setNextMessageOriginIsVoice(true);
                            if (autoSend && transcript.trim().isNotEmpty) {
                              _sendMessageUtil(transcript.trim());
                            }
                          },
                          onClose: () {
                            voiceRecorderProvider.close();
                          },
                        ),
                      )
                    else
                      Theme(
                        data: Theme.of(context).copyWith(
                          textSelectionTheme: TextSelectionThemeData(
                            selectionColor: OmiColors.textSecondary.withValues(alpha: 0.4),
                            selectionHandleColor: OmiColors.textPrimary,
                          ),
                        ),
                        child: TextField(
                          key: const ValueKey('omi.chat.input'),
                          enabled: true,
                          controller: textController,
                          focusNode: textFieldFocusNode,
                          obscureText: false,
                          textAlign: TextAlign.start,
                          decoration: InputDecoration(
                            hintText: context.l10n.askAnything,
                            hintStyle: OmiType.callout.copyWith(color: OmiColors.textTertiary),
                            border: InputBorder.none,
                            focusedBorder: InputBorder.none,
                            enabledBorder: InputBorder.none,
                            contentPadding: const EdgeInsets.only(top: 6, bottom: 4, right: 10),
                            isDense: true,
                          ),
                          minLines: 1,
                          maxLines: 8,
                          keyboardType: TextInputType.multiline,
                          textCapitalization: TextCapitalization.sentences,
                          style: OmiType.callout.copyWith(height: 1.3),
                        ),
                      ),
                    Row(
                      children: [
                        Transform.translate(
                          // The 36pt circle sits on the card's inner margin, not the 44pt target's.
                          offset: const Offset(-10, 0),
                          child: voiceActive
                              ? ChatComposerSideButton(
                                  key: const ValueKey('omi.chat.voice.discard'),
                                  icon: const Icon(Icons.close),
                                  label: context.l10n.chatDiscardRecording,
                                  onPressed: () {
                                    OmiHaptics.light();
                                    voiceRecorderProvider.discardRecording();
                                  },
                                )
                              : _buildAttachButton(context, provider),
                        ),
                        if (!voiceActive)
                          Transform.translate(offset: const Offset(-10, 0), child: _buildAppChip(context, provider)),
                        const Spacer(),
                        // Stop fills the draft; Send transcribes and sends.
                        if (recording)
                          ChatComposerRoundButton(
                            buttonKey: const ValueKey('omi.chat.voice.transcribe'),
                            icon: const Icon(Icons.stop),
                            label: context.l10n.stopRecording,
                            onPressed: () {
                              OmiHaptics.light();
                              voiceRecorderProvider.processRecording();
                            },
                          ),
                        if (recording)
                          ChatComposerRoundButton(
                            buttonKey: const ValueKey('omi.chat.voice.send'),
                            icon: const FaIcon(FontAwesomeIcons.arrowUp),
                            label: context.l10n.chatSendMessage,
                            onPressed: () {
                              OmiHaptics.medium();
                              voiceRecorderProvider.requestAutoSendOnNextTranscript();
                              voiceRecorderProvider.processRecording();
                            },
                          ),
                        if (!voiceActive && textController.text.isEmpty)
                          ChatComposerRoundButton(
                            icon: const FaIcon(FontAwesomeIcons.microphone),
                            label: context.l10n.startVoiceRecording,
                            onPressed: () {
                              OmiHaptics.light();
                              FocusScope.of(context).unfocus();
                              voiceRecorderProvider.startRecording();
                            },
                          ),
                        // Send — only with text and not in voice mode. Offline or uploading it
                        // stays visible but is drawn disabled.
                        if (!voiceActive && !provider.sendingMessage)
                          ValueListenableBuilder<TextEditingValue>(
                            valueListenable: textController,
                            builder: (context, value, child) {
                              final hasText = value.text.trim().isNotEmpty;
                              if (!hasText) return const SizedBox.shrink();
                              final canSend = hasText &&
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
                                        final message = textController.text.trim();
                                        if (message.isEmpty) return;
                                        _sendMessageUtil(message);
                                      }
                                    : null,
                              );
                            },
                          ),
                      ],
                    ),
                  ],
                ),
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildAttachButton(BuildContext context, MessageProvider provider) {
    return PullDownButton(
      itemBuilder: (context) => [
        PullDownMenuItem(
          title: context.l10n.takePhoto,
          iconWidget: const FaIcon(FontAwesomeIcons.camera, size: 16),
          onTap: () {
            OmiHaptics.selection();
            if (mounted) this.context.read<MessageProvider>().captureImage();
          },
        ),
        PullDownMenuItem(
          title: context.l10n.photoLibrary,
          iconWidget: const FaIcon(FontAwesomeIcons.images, size: 16),
          onTap: () {
            OmiHaptics.selection();
            if (mounted) this.context.read<MessageProvider>().selectImage();
          },
        ),
        PullDownMenuItem(
          title: context.l10n.chooseFile,
          iconWidget: const FaIcon(FontAwesomeIcons.folder, size: 16),
          onTap: () {
            OmiHaptics.selection();
            if (mounted) this.context.read<MessageProvider>().selectFile();
          },
        ),
      ],
      position: PullDownMenuPosition.automatic,
      buttonBuilder: (context, showMenu) => ChatComposerSideButton(
        icon: const FaIcon(FontAwesomeIcons.paperclip),
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
    );
  }

  /// Omi, or the chat app picked for this thread; opens the chat apps drawer.
  Widget _buildAppChip(BuildContext context, MessageProvider provider) {
    return Consumer<AppProvider>(
      builder: (context, appProvider, _) {
        final selectedApp = provider.chatApps.firstWhereOrNull((app) => app.id == appProvider.selectedChatAppId);
        return ChatAppChip(
          name: selectedApp != null ? selectedApp.getName() : context.l10n.omiAppName,
          avatar: selectedApp != null ? ChatAppAvatar(app: selectedApp) : const ChatOmiAvatar(),
          onPressed: () {
            OmiHaptics.selection();
            // Dismiss the keyboard before opening the drawer, once the scaffold has settled.
            FocusScope.of(context).unfocus();
            WidgetsBinding.instance.addPostFrameCallback((_) => scaffoldKey.currentState?.openEndDrawer());
          },
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
    if (next == null) {
      if (_chatScrollMode == ChatScrollMode.freeScrolling && (isUserScroll || isDragScroll)) {
        _showLatestJumpOnActivity();
      }
      return false;
    }

    _chatScrollMode = next;
    _cancelPendingScrolls();
    if (next == ChatScrollMode.freeScrolling) {
      _showLatestJumpOnActivity();
    } else {
      _latestJumpIdleTimer?.cancel();
      _showLatestJump = false;
    }
    if (mounted) setState(() {});
    return false;
  }

  void _showLatestJumpOnActivity() {
    _latestJumpIdleTimer?.cancel();
    if (!_showLatestJump) {
      _showLatestJump = true;
      if (mounted) setState(() {});
    }
    _latestJumpIdleTimer = Timer(const Duration(milliseconds: 2500), () {
      if (!mounted || _chatScrollMode != ChatScrollMode.freeScrolling) return;
      setState(() => _showLatestJump = false);
    });
  }

  Widget _buildJumpToLatestButton() {
    return ChatJumpToLatestButton(label: context.l10n.latest, onTap: () => _resumeFollowingAndScroll(animated: true));
  }

  void scrollToBottomOnSend() {
    _resumeFollowingAndScroll(animated: true);
  }

  void _resumeFollowingAndScroll({int delayMs = 0, bool animated = false}) {
    _cancelPendingScrolls();
    _latestJumpIdleTimer?.cancel();
    _showLatestJump = false;
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

  /// A close X and a grabber; a swipe down on the header closes the sheet (docs/ux-contract.md D1).
  PreferredSizeWidget _buildAppBar(BuildContext context, MessageProvider provider) {
    final l10n = context.l10n;
    final loading = provider.isLoadingMessages;
    return PreferredSize(
      preferredSize: Size.fromHeight(kToolbarHeight + (loading ? 32 : 0)),
      child: GestureDetector(
        behavior: HitTestBehavior.translucent,
        onVerticalDragEnd: (details) {
          if ((details.primaryVelocity ?? 0) > 300) Navigator.of(context).maybePop();
        },
        child: AppBar(
          elevation: 0,
          scrolledUnderElevation: 0,
          backgroundColor: Colors.transparent,
          surfaceTintColor: Colors.transparent,
          automaticallyImplyLeading: false,
          leading: const Center(child: OmiCloseButton.circled()),
          // The chat apps drawer opens from the composer's app chip, not a header menu button.
          actions: const [SizedBox.shrink()],
          flexibleSpace: SafeArea(
            bottom: false,
            child: Align(
              alignment: Alignment.topCenter,
              child: Container(
                margin: const EdgeInsets.only(top: 6),
                width: 36,
                height: 4,
                decoration: BoxDecoration(color: OmiColors.border, borderRadius: OmiRadius.pillAll),
              ),
            ),
          ),
          bottom: loading
              ? PreferredSize(
                  preferredSize: const Size.fromHeight(32),
                  child: SizedBox(
                    width: double.infinity,
                    height: 32,
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
        ),
      ),
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
            ExcludeSemantics(child: Icon(Icons.cloud_off_rounded, size: 14, color: OmiColors.textTertiary)),
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
                    Icon(Icons.close, size: 14, color: OmiColors.textSecondary),
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
        decoration: BoxDecoration(color: OmiColors.surface2, borderRadius: OmiRadius.lgAll),
        padding: const EdgeInsets.only(left: OmiSpacing.sm),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            ExcludeSemantics(
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
