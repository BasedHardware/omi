part of 'page.dart';

extension _NativeConversationDetail on ConversationDetailPageState {
  void _nativePlaybackChanged() {
    if (mounted && _nativeDetail) _nativeRebuild(() {});
  }

  /// A native presentation this page needs is unavailable: the complete classic page takes over,
  /// with its own title field, search field, summary editor and menu.
  void _restoreClassicDetail() {
    if (mounted && !_nativeDetailRestored) _nativeRebuild(() => _nativeDetailRestored = true);
  }

  /// The native summary editor is unavailable: the classic page takes over and opens its in-place
  /// editor on [selection]. The request lasts only for the frame that mounts that editor.
  void _editSummaryClassically(ConversationSummarySelection selection) {
    if (!mounted) return;
    _nativeRebuild(() {
      _nativeDetailRestored = true;
      _classicSummaryEdit = selection;
    });
    WidgetsBinding.instance.addPostFrameCallback((_) => _classicSummaryEdit = null);
  }

  /// Opens the classic page's More menu where its button sits.
  void _showClassicDetailMenu(ConversationDetailProvider provider) {
    final width = MediaQuery.sizeOf(context).width;
    final top = MediaQuery.paddingOf(context).top + (kToolbarHeight - kOmiMinTapTarget) / 2;
    final left = Directionality.of(context) == TextDirection.rtl ? 0.0 : width - kOmiMinTapTarget;
    unawaited(showPullDownMenu(
        context: context,
        items: _menuItems(context, provider),
        position: Rect.fromLTWH(left, top, kOmiMinTapTarget, kOmiMinTapTarget)));
  }

  void _acceptNativeSections(String id, List<NativeSection> sections) {
    if (!mounted) return;
    final value = jsonEncode(sections.map((section) => section.projection).toList());
    _nativeSections[id] = sections;
    if (_nativeValues[id] == value) return;
    _nativeValues[id] = value;
    _nativeRebuild(() {});
  }

  void _acceptNativePlayback(List<NativeRow> rows) {
    if (!mounted) return;
    final value = jsonEncode(rows.map((row) => row.projection).toList());
    _nativePlayback = rows;
    if (_nativePlaybackValue == value) return;
    _nativePlaybackValue = value;
    _nativeRebuild(() {});
  }

  Future<bool> _renameNative(ConversationDetailProvider provider) async {
    final conversation = provider.conversation;
    final original = conversation.structured.title;
    if (original.characters.length > 10000) return false;
    final result =
        await showIosNativeModal(context, title: context.l10n.renameConversation, guardEdits: true, sections: [
      NativeSection(
          'rename', [NativeRow('rename_title', context.l10n.renameConversation, kind: 'text', value: original)])
    ], actions: [
      NativeRow('cancel', context.l10n.cancel),
      NativeRow('save', context.l10n.save, symbol: 'checkmark')
    ]);
    if (result == null) {
      // No native editor: the classic page's title field takes the rename instead.
      if (!mounted) return true;
      _restoreClassicDetail();
      return false;
    }
    final text = result.values['rename_title'];
    if (!mounted ||
        result.action != 'save' ||
        text is! String ||
        provider.conversationOrNull?.id != conversation.id ||
        provider.conversation.structured.title != original) {
      return true;
    }
    final saved = await provider.saveTitle(text);
    if (!mounted) return true;
    if (saved == true) {
      OmiFeedback.confirm(context, context.l10n.saved);
    } else if (saved == false) {
      OmiFeedback.error(context, context.l10n.failedToSaveCheckConnection);
    }
    return true;
  }

  Future<void> _nativeDetailMenu(ConversationDetailProvider provider) async {
    final conversationId = provider.conversation.id;
    HapticFeedback.mediumImpact();
    PlatformManager.instance.analytics.conversationThreeDotsMenuOpened(conversationId: provider.conversation.id);
    final items = <PullDownMenuItem>[];
    for (final entry in _menuItems(context, provider)) {
      if (entry is PullDownMenuItem) items.add(entry);
      if (entry is PullDownMenuActionsRow) items.addAll(entry.items);
    }
    final result = await showIosNativeModal(context, title: context.l10n.moreOptions, actions: [
      for (final (index, item) in items.indexed)
        NativeRow('detail_menu_$index', item.title,
            subtitle: item.subtitle ?? '',
            enabled: item.enabled && item.onTap != null,
            destructive: item.isDestructive),
      NativeRow('cancel', context.l10n.cancel),
    ]);
    if (!mounted || provider.conversationOrNull?.id != conversationId) return;
    if (result == null) {
      // No native menu: the complete page takes over and opens its own.
      _restoreClassicDetail();
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && provider.conversationOrNull?.id == conversationId) _showClassicDetailMenu(provider);
      });
      return;
    }
    if (result.action == null) return;
    final index = int.tryParse(result.action!.replaceFirst('detail_menu_', ''));
    if (index == null || index < 0 || index >= items.length) return;
    final item = items[index];
    if (item.title == context.l10n.search) {
      trackConversationAction(ConversationActionAction.search, ConversationActionSurface.overflow);
      PlatformManager.instance.analytics.conversationDetailSearchClicked(conversationId: provider.conversation.id);
      final query = await showIosNativeModal(context, title: context.l10n.search, sections: [
        NativeSection(
            'detail_search_editor', [NativeRow('query', context.l10n.search, kind: 'text', value: _searchQuery)]),
      ], actions: [
        NativeRow('cancel', context.l10n.cancel),
        NativeRow('search', context.l10n.search)
      ]);
      if (!mounted || provider.conversationOrNull?.id != conversationId) return;
      if (query == null) {
        // No native search editor: the complete page opens its search field instead.
        _restoreClassicDetail();
        _nativeRebuild(() => _isSearching = true);
        _searchFocusNode.requestFocus();
      } else if (query.action == 'search' && query.values['query'] is String) {
        _onSearchChanged(query.values['query'] as String);
      }
    } else {
      item.onTap?.call();
    }
  }

  String? _nativeSearchTarget(ServerConversation conversation) {
    if (_searchQuery.isEmpty || _currentSearchIndex <= 0) return null;
    var match = _currentSearchIndex;
    if (selectedTab == ConversationTab.summary) {
      final blocks =
          nativeRichText(context.read<ConversationDetailProvider>().getSummarySelection().content.decodeString);
      for (final (index, block) in blocks.indexed) {
        var offset = 0;
        final text = nativeRichBlockText(block).toLowerCase();
        while ((offset = text.indexOf(_searchQuery.toLowerCase(), offset)) >= 0) {
          if (--match == 0) return index == 0 ? 'detail_summary_content' : 'detail_summary_content:$index';
          offset += _searchQuery.length;
        }
      }
      return null;
    }
    for (final segment in conversation.transcriptSegments) {
      var offset = 0;
      final text = segment.text.toLowerCase();
      while ((offset = text.indexOf(_searchQuery.toLowerCase(), offset)) >= 0) {
        if (--match == 0) return 'detail_segment:${segment.id}';
        offset += _searchQuery.length;
      }
    }
    return null;
  }

  Widget _nativeDetailSurface(
      ConversationDetailProvider provider, ServerConversation conversation, bool hasBar, Widget classic) {
    if (!_nativeDetail) return classic;
    // Oversized editors retain the complete existing surface until its larger input contract is migrated.
    if (provider.getSummarySelection().content.characters.length > 10000 ||
        conversation.structured.title.characters.length > 10000) {
      return classic;
    }
    final l10n = context.l10n;
    final title = conversation.discarded
        ? l10n.discardedConversation
        : conversation.structured.title.trim().isNotEmpty
            ? conversation.structured.title
            : transcriptFallbackTitle(conversation) ??
                recordingFallbackTitle(conversation, l10n, dates: OmiDateFormat.of(context));
    final dates = OmiDateFormat.of(context);
    final start = conversation.startedAt ?? conversation.createdAt;
    final duration = conversationDurationLabel(conversation, l10n);
    final recordings = CaptureGroupPresentation.recordings(conversation);
    final folder = context.watch<FolderProvider?>()?.getFolderById(conversation.folderId ?? '');
    final participants = ConversationDetailMeta.participants(conversation.transcriptSegments,
        you: l10n.you,
        personName: (id) => SharedPreferencesUtil().getPersonById(id)?.name,
        speakers: conversation.speakerResolution);
    final people = ConversationDetailMeta.peopleLabel(participants.named, participants.unnamed,
        uncounted: participants.uncounted,
        summary: (first, others) => l10n.participantsSummary(first, others),
        uncountedSummary: l10n.participantsSummaryUncounted);
    final sections = <NativeSection>[
      NativeSection('detail_header', [
        NativeRow('detail_title', title, kind: 'label'),
        NativeRow('detail_when',
            ['${dates.dayHeader(start)} ${dates.time(start)}', if (duration.isNotEmpty) duration].join(' · '),
            kind: conversation.calendarEvent == null ? 'label' : 'button',
            symbol: 'calendar',
            action: conversation.calendarEvent == null
                ? null
                : (_) => showCalendarEventDetailsSheet(context, conversation.calendarEvent!,
                    onUnlink: provider.unlinkCalendarEvent)),
        if (conversation.captureCoverage == 'incomplete')
          NativeRow('detail_partial_recording', l10n.partialRecording, kind: 'label', symbol: 'mic'),
        if (folder != null)
          NativeRow('detail_folder', folder.name, symbol: 'folder', action: (_) {
            trackConversationAction(ConversationActionAction.moveFolder, ConversationActionSurface.detailBody);
            return showConversationFolderSheet(context, conversation, source: 'detail_page_sheet');
          }),
        if (people != null) NativeRow('detail_people', people, kind: 'label'),
        if (recordings.isNotEmpty)
          NativeRow('detail_recordings', l10n.recordings, symbol: 'square.stack', action: (_) {
            trackConversationAction(ConversationActionAction.recordingsOpen, ConversationActionSurface.detailBody);
            _openRecordings(recordings);
          }),
        NativeRow('detail_tab', l10n.conversations,
            kind: 'segmented',
            value: selectedTab.name,
            options: {ConversationTab.summary.name: l10n.summary, ConversationTab.transcript.name: l10n.transcript},
            action: (value) {
          _hasExplicitTabSelection = true;
          _controller!.animateTo(value == ConversationTab.transcript.name ? _transcriptTabIndex : _summaryTabIndex);
        }),
        if (provider.isReprocessingOpenConversation || conversation.status == ConversationStatus.processing)
          NativeRow(
              'detail_processing',
              provider.isReprocessingOpenConversation
                  ? l10n.reprocessingConversationProgress
                  : l10n.processingConversationProgress,
              kind: 'label'),
      ]),
      ...?_nativeSections[selectedTab == ConversationTab.summary ? 'summary' : 'transcript'],
    ];
    final contentIds = sections.expand((section) => section.rows).map((row) => row.id).toSet();
    final searching = _searchQuery.isNotEmpty;
    final requested = searching
        ? _nativeSearchTarget(conversation)
        : _playbackController.followTargetSegmentId == null
            ? null
            : 'detail_segment:${_playbackController.followTargetSegmentId}';
    final current =
        _playbackController.currentSegmentId == null ? null : 'detail_segment:${_playbackController.currentSegmentId}';
    final hasContent = _nativeSections[selectedTab == ConversationTab.summary ? 'summary' : 'transcript'] != null;
    return Scaffold(
        body: KeyedSubtree(
            key: _nativeShareKey,
            child: IosNativeSurface(
              title: title,
              fallback: classic,
              loading: !hasContent,
              searchValue: _searchQuery,
              searchPlaceholder: l10n.search,
              search: (value) => _onSearchChanged(value as String),
              onRefresh: (_) => provider.refreshConversation(trackLoad: true),
              sections: sections,
              toolbar: [
                NativeRow('detail_back', l10n.back,
                    symbol: 'chevron.left', action: (_) => Navigator.of(context).maybePop()),
                NativeRow('detail_star', conversation.starred ? l10n.unstarConversation : l10n.starConversation,
                    symbol: conversation.starred ? 'star.fill' : 'star', enabled: !_isTogglingStarred, action: (_) {
                  trackConversationAction(
                      conversation.starred ? ConversationActionAction.unstar : ConversationActionAction.star,
                      ConversationActionSurface.topBar);
                  return _toggleStarred(provider);
                }),
                NativeRow('detail_share', l10n.share, symbol: 'square.and.arrow.up', enabled: !_isSharing, action: (_) {
                  trackConversationAction(ConversationActionAction.share, ConversationActionSurface.topBar);
                  return _shareConversation(provider);
                }),
                NativeRow('detail_more', l10n.moreOptions,
                    symbol: 'ellipsis', action: (_) => _nativeDetailMenu(provider)),
              ],
              reader: NativeReader(
                  currentId: contentIds.contains(current) ? current : null,
                  targetId: contentIds.contains(requested) ? requested : null,
                  request: searching ? _nativeSearchRequest : _playbackController.followRequest,
                  following: searching ||
                      _playbackController.isFollowing &&
                          (_playbackController.isPlaying || _playbackController.followRequest > 0),
                  footer: [
                    if (hasBar) ..._nativePlayback,
                    if (searching) ...[
                      NativeRow('detail_search_count', '$_currentSearchIndex / $_totalSearchResults', kind: 'label'),
                      NativeRow('detail_search_previous', l10n.previousResult,
                          symbol: 'chevron.up',
                          enabled: _totalSearchResults > 0,
                          action: (_) => _navigateSearch(false)),
                      NativeRow('detail_search_next', l10n.nextResult,
                          symbol: 'chevron.down',
                          enabled: _totalSearchResults > 0,
                          action: (_) => _navigateSearch(true)),
                      NativeRow('detail_search_close', l10n.close, symbol: 'xmark', action: (_) => _closeSearch()),
                    ],
                  ],
                  scroll: selectedTab == ConversationTab.transcript && hasContent
                      ? NativeRow('detail_reader_scroll', l10n.transcript, kind: 'menu', options: {
                          'suspend': l10n.transcript,
                          for (final segment in conversation.transcriptSegments)
                            if (contentIds.contains('detail_segment:${segment.id}'))
                              'detail_segment:${segment.id}': segment.text
                        }, action: (value) {
                          if (value == 'suspend') {
                            _playbackController.suspendFollowing();
                          } else {
                            final segment = provider.conversation.transcriptSegments
                                .where((segment) => 'detail_segment:${segment.id}' == value)
                                .firstOrNull;
                            if (segment != null) {
                              _playbackController.readerMovedTo(segment);
                            }
                          }
                        })
                      : null),
              nativeWrapper: (view) => AppReviewPrompt(
                  contentId: conversation.id,
                  moment: AppReviewMoment.conversationRead,
                  enabled: hasContent &&
                      !widget.isFromOnboarding &&
                      widget.initialSeekStart == null &&
                      selectedTab == ConversationTab.summary &&
                      !_controller!.indexIsChanging &&
                      !_isSearching &&
                      !_isSharing &&
                      !_isDownloadingAudio &&
                      !_reviewInterrupted &&
                      !provider.isLoading &&
                      !provider.loadingReprocessConversation &&
                      conversation.status == ConversationStatus.completed &&
                      !conversation.discarded &&
                      provider.getSummarySelection().content.trim().isNotEmpty,
                  child: view),
              nativeOwner: SizedBox(
                  height: MediaQuery.sizeOf(context).height,
                  child: Column(children: [
                    const ConversationActivityStrip(),
                    Expanded(
                        child: SummaryTab(
                            key: ValueKey('native-summary-owner:${conversation.id}'),
                            onNativePresentation: (sections) => _acceptNativeSections('summary', sections),
                            onNativeUnavailable: _editSummaryClassically,
                            onNativeInteraction: () {
                              if (mounted) _nativeRebuild(() => _reviewInterrupted = true);
                            })),
                    Expanded(
                        child: TranscriptWidgets(
                            key: ValueKey('native-transcript-owner:${conversation.id}'),
                            onNativePresentation: (sections) => _acceptNativeSections('transcript', sections),
                            playbackController: _playbackController,
                            onSegmentTap: (segment) async {
                              if (selectedTab != ConversationTab.transcript) {
                                _controller!.animateTo(_transcriptTabIndex);
                              }
                              await _seekToSegmentCallback?.call(segment.start, segment.end);
                            })),
                    ConversationBottomBar(
                        key: const ValueKey('native-detail-player-owner'),
                        onNativePresentation: _acceptNativePlayback,
                        onAudioInteraction: () {
                          if (mounted && !_reviewInterrupted) _nativeRebuild(() => _reviewInterrupted = true);
                        },
                        mode: ConversationBottomBarMode.detail,
                        onAskOmi: () => _openAskOmi(provider),
                        selectedTab: selectedTab,
                        conversation: conversation,
                        hasSegments: hasBar,
                        playbackController: _playbackController,
                        onSeekFunctionReady: (seek) {
                          WidgetsBinding.instance.addPostFrameCallback((_) {
                            if (mounted) {
                              _seekToSegmentCallback = seek;
                              _maybePlayInitialSeek();
                            }
                          });
                        },
                        onTabSelected: (tab) {
                          _hasExplicitTabSelection = true;
                          _controller!.animateTo(ConversationDetailPageState._indexForTab(tab));
                        },
                        onStopPressed: () {}),
                  ])),
            )));
  }
}
