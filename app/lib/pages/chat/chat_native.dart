part of 'page.dart';

extension _ChatPageNative on ChatPageState {
  Widget _buildNative(Widget classic, MessageProvider provider, ConnectivityProvider connectivityProvider) {
    if (!nativePresentationEnabled) return classic;
    // Native rows, and the provider reads they watch, exist only once the renderer is supported.
    return FutureBuilder<bool>(
      future: _nativeSupport,
      builder: (context, support) {
        if (support.connectionState != ConnectionState.done) return const OmiLoadingState();
        if (support.data != true) return classic;
        final voice = context.watch<VoiceRecorderProvider>();
        final latest = provider.messages.lastOrNull;
        final followup = latest?.sender == MessageSender.ai &&
                !provider.chatMutationInProgress &&
                !provider.isReplyFailed(latest!) &&
                connectivityProvider.isConnected &&
                !voice.isActive &&
                !provider.isUploadingFiles
            ? latest.followUpQuestion
            : null;
        final l10n = context.l10n;
        final greeting = DateTime.now().hour < 12
            ? l10n.greetingMorning
            : DateTime.now().hour < 18
                ? l10n.greetingAfternoon
                : l10n.greetingEvening;
        return IosNativeSurface(
          title: context.watch<AppProvider>().getSelectedApp()?.getName() ?? l10n.askOmi,
          fallback: classic,
          nativeOwner: voice.isActive
              ? NativeChatVoiceOwner(
                  onTranscriptReady: (transcript, autoSend) {
                    if (!mounted) return;
                    _updateNative(() => textController.text = transcript);
                    voice.close();
                    provider.setNextMessageOriginIsVoice(true);
                    if (autoSend && transcript.trim().isNotEmpty) _sendMessageUtil(transcript.trim());
                  },
                  onClose: voice.close,
                )
              : null,
          loading: provider.isLoadingMessages || provider.isClearingChat,
          failed: provider.historyProblem != null,
          empty: l10n.greetingWithName(greeting, prefs.givenName),
          onRefresh: (_) => provider.refreshMessages(),
          sections: [
            NativeSection('chat_messages', [
              if (provider.hasOlderMessages)
                NativeRow(
                  'chat_older',
                  l10n.showMore,
                  enabled: !provider.loadingOlderMessages && provider.canSwitchChat,
                  action: (_) => provider.loadOlderMessages(),
                ),
              ..._nativeTranscript.rows(
                context,
                provider,
                ChatNativeActions(
                  send: _sendMessageUtil,
                  askOmi: (text) => _updateNative(() => _selectedContext = text),
                  retry: _retryReply,
                  setMessageNps: provider.setMessageNps,
                  updateConversation: (conversation) =>
                      context.read<ConversationProvider>().updateConversation(conversation),
                ),
              ),
              for (final file in provider.selectedFiles)
                NativeRow(
                  'chat_selected_file_${file.path}',
                  file.uri.pathSegments.last,
                  kind: 'menu',
                  imageUri: provider.selectedFileTypes[provider.selectedFiles.indexOf(file)] == 'image'
                      ? file.uri.toString()
                      : null,
                  subtitle: provider.isFileUploading(file.path) ? l10n.loading : l10n.removeAttachment,
                  options: {'remove': l10n.removeAttachment},
                  action: (_) => provider.clearSelectedFile(
                    provider.selectedFiles.indexOf(file),
                  ),
                ),
              if (_chatScope != null)
                NativeRow(
                  'chat_scope',
                  l10n.chatScopeAbout(
                    _chatScope!.title ?? l10n.conversationTab,
                  ),
                  action: (_) => _updateNative(() => _chatScope = null),
                ),
              if (_selectedContext != null)
                NativeRow(
                  'chat_context',
                  _selectedContext!,
                  action: (_) => _updateNative(() => _selectedContext = null),
                ),
              if (provider.messages.isEmpty && connectivityProvider.isConnected) ...[
                for (final prompt in [
                  l10n.askSuggestDecide,
                  l10n.askSuggestOwe,
                  l10n.askSuggestNotice,
                ])
                  NativeRow(
                    'chat_prompt_$prompt',
                    prompt,
                    action: (_) => _updateNative(() => textController.text = prompt),
                  ),
              ],
            ]),
          ],
          toolbar: [
            NativeRow(
              'chat_close',
              l10n.close,
              symbol: 'xmark',
              action: (_) => Navigator.of(context).pop(),
            ),
            NativeRow(
              'chat_options',
              l10n.chatAppsTitle,
              symbol: 'ellipsis',
              action: (_) => _openNativeChatOptions(),
            ),
          ],
          chat: NativeChat(
            draft: textController.text,
            placeholder: l10n.askOmi,
            streaming: provider.chatMutationInProgress,
            followup: followup ?? '',
            actions: [
              if (voice.isActive) ...nativeVoiceRows(context, voice),
              if (!voice.isActive) ...[
                NativeRow(
                  'chat_draft',
                  l10n.askOmi,
                  kind: 'text',
                  value: textController.text,
                  action: (value) => _updateNative(() => textController.text = value as String),
                ),
                NativeRow(
                  'chat_attach',
                  l10n.chatAddAttachment,
                  kind: 'menu',
                  symbol: 'paperclip',
                  options: {
                    'camera': l10n.takePhoto,
                    'photos': l10n.photoLibrary,
                    'file': l10n.chooseFile,
                  },
                  enabled: connectivityProvider.isConnected &&
                      !provider.chatMutationInProgress &&
                      provider.selectedFiles.length < 4,
                  action: (value) {
                    switch (value) {
                      case 'camera':
                        provider.captureImage();
                      case 'photos':
                        provider.selectImage();
                      case 'file':
                        provider.selectFile();
                    }
                  },
                ),
                if (textController.text.trim().isEmpty)
                  NativeRow(
                    'chat_voice',
                    l10n.startVoiceRecording,
                    symbol: 'mic',
                    enabled: connectivityProvider.isConnected && !provider.chatMutationInProgress,
                    action: (_) => voice.startRecording(),
                  ),
                NativeRow(
                  'chat_send',
                  l10n.chatSendMessage,
                  symbol: 'arrow.up',
                  enabled: textController.text.trim().isNotEmpty &&
                      connectivityProvider.isConnected &&
                      !provider.chatMutationInProgress &&
                      !provider.isUploadingFiles &&
                      !provider.isLoadingMessages,
                  action: (_) => _sendMessageUtil(textController.text.trim()),
                ),
                if (followup != null)
                  NativeRow(
                    'chat_followup',
                    followup,
                    symbol: 'sparkles',
                    action: (_) => _sendMessageUtil(followup),
                  ),
              ],
            ],
          ),
        );
      },
    );
  }

  Future<void> _openNativeChatOptions() => showOmiSheet<void>(
        context: context,
        builder: (_) => SizedBox(
          height: MediaQuery.sizeOf(context).height * .8,
          child: _chatAppsDrawer(),
        ),
        nativeBuilder: (_) => _chatAppsDrawer(sheet: true),
      );
}
