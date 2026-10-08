part of 'summary_tab.dart';

/// The rich summary rows. A link opens only when it is one of this Markdown's own links, through the
/// Dart URL owner; the native reader discards every other URL instead of opening it itself.
@visibleForTesting
List<NativeRow> nativeSummaryContentRows(String markdown, {Future<bool> Function(Uri url) open = _openSummaryLink}) {
  final links = nativeRichTextLinks(markdown);
  return [
    for (final (index, block) in nativeRichText(markdown).indexed)
      NativeRow(index == 0 ? 'detail_summary_content' : 'detail_summary_content:$index', nativeRichBlockText(block),
          kind: 'rich_text',
          blocks: [block],
          options: links,
          action: links.isEmpty
              ? null
              : (value) async {
                  final url = value is String && links.containsKey(value) ? Uri.tryParse(links[value]!) : null;
                  // A generated summary may only hand off web links; other schemes are ignored.
                  if (url != null && ['http', 'https'].contains(url.scheme)) await open(url);
                }),
  ];
}

Future<bool> _openSummaryLink(Uri url) => launchUrl(url, mode: LaunchMode.externalApplication);

extension _NativeSummaryPresentation on _SummaryTabState {
  void _acceptNativeContribution(String id, List<NativeRow> rows) {
    if (!mounted) return;
    final value = jsonEncode(rows.map((row) => row.projection).toList());
    _nativeContributions[id] = rows;
    if (_nativeContributionValues[id] == value) return;
    _nativeContributionValues[id] = value;
    _nativeRebuild(() {});
  }

  void _publishNativeSummary() {
    if (_nativeScheduled || widget.onNativePresentation == null) return;
    _nativeScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _nativeScheduled = false;
      if (!mounted || widget.onNativePresentation == null) return;
      final provider = context.read<ConversationDetailProvider>();
      final conversation = provider.conversation;
      final selection = provider.getSummarySelection();
      final l10n = context.l10n;
      final rows = <NativeRow>[];
      if (conversation.discarded || selection.kind == ConversationSummaryKind.empty) {
        final processing =
            provider.isReprocessingOpenConversation || conversation.status == ConversationStatus.processing;
        final retry = conversation.showsSummaryRetry || conversation.status == ConversationStatus.failed;
        rows.add(NativeRow(
            'detail_summary_status',
            processing
                ? l10n.summarizingConversation
                : conversation.discarded
                    ? l10n.nothingInterestingRetry
                    : retry
                        ? l10n.conversationSummaryFailed
                        : l10n.noSummaryForConversation,
            kind: 'label'));
        if (!processing) {
          rows.add(NativeRow(
              'detail_summary_generate',
              conversation.discarded
                  ? l10n.summarize
                  : retry
                      ? l10n.retry
                      : l10n.generateSummary,
              enabled: !provider.loadingReprocessConversation,
              action: (_) => conversation.discarded || retry
                  ? provider.reprocessConversation()
                  : showSummarizedAppsSheet(context)));
        }
      } else {
        rows.addAll(nativeSummaryContentRows(selection.content.decodeString));
        if (selection.canEdit(conversation)) {
          rows.add(NativeRow('detail_summary_edit', l10n.edit,
              symbol: 'pencil',
              enabled: !_isEditing && !provider.loadingReprocessConversation,
              action: (_) => _editNativeSummary(selection)));
        }
      }
      final geolocation = conversation.discarded ? null : conversation.geolocation;
      if (geolocation?.latitude != null && geolocation?.longitude != null) {
        rows.add(NativeRow('detail_summary_location', geolocation?.address ?? l10n.unknownLocation,
            symbol: 'mappin', action: (_) => MapsUtil.launchMap(geolocation!.latitude!, geolocation.longitude!)));
      }
      final feedbackKind = feedbackPromptKindForTarget(
          targetId: conversation.id,
          hasSummary: !conversation.discarded && !selection.isApp && selection.content.trim().isNotEmpty,
          hasRecording: !conversation.discarded &&
              conversation.status == ConversationStatus.completed &&
              conversation.audioFiles.isNotEmpty);
      if (!conversation.discarded && conversation.status == ConversationStatus.completed) {
        rows.addAll(_nativeContributions['screenshots'] ?? []);
      }
      if (feedbackKind == FeedbackPromptKind.summary) rows.addAll(_nativeContributions['summary_feedback'] ?? []);
      if (feedbackKind == FeedbackPromptKind.recording) rows.addAll(_nativeContributions['recording_feedback'] ?? []);
      widget.onNativePresentation!([NativeSection('detail_summary', rows, title: l10n.summary)]);
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }

  Future<void> _editNativeSummary(ConversationSummarySelection selection) async {
    final provider = context.read<ConversationDetailProvider>();
    if (_isEditing || !selection.canEdit(provider.conversation) || provider.loadingReprocessConversation) return;
    if (!context.read<ConnectivityProvider>().isConnected) {
      ConnectivityProvider.showNoInternetDialog(context);
      return;
    }
    final conversationId = provider.conversation.id;
    widget.onNativeInteraction?.call();
    _nativeRebuild(() => _isEditing = true);
    PlatformManager.instance.analytics.editSummaryStarted();
    NativeModalResult? result;
    try {
      result = await showIosNativeModal(context, title: context.l10n.summary, guardEdits: true, sections: [
        NativeSection('summary_editor',
            [NativeRow('summary_content', context.l10n.summary, kind: 'text', value: selection.content, enabled: true)])
      ], actions: [
        NativeRow('cancel', context.l10n.cancel),
        NativeRow('save', context.l10n.save, symbol: 'checkmark')
      ]);
    } finally {
      if (mounted) _nativeRebuild(() => _isEditing = false);
    }
    if (!mounted) return;
    if (result == null) {
      // No native editor: the complete page takes over and continues this edit in place.
      widget.onNativeUnavailable?.call(selection);
      return;
    }
    final text = result.values['summary_content'];
    if (result.action == 'save' &&
        text is String &&
        text != selection.content &&
        provider.conversationOrNull?.id == conversationId &&
        selection.canEdit(provider.conversation)) {
      PlatformManager.instance.analytics.editSummarySaved();
      await provider.saveEditingSummarySelection(selection, text);
    } else {
      PlatformManager.instance.analytics.editSummaryCancelled();
    }
  }
}
