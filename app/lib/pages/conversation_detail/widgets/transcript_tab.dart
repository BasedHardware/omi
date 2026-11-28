import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'package:pull_down_button/pull_down_button.dart';
import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart' show assignBulkConversationTranscriptSegments;
import 'package:omi/backend/http/api/speaker_labels.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/conversation_v3.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_detail/widgets/transcript_line_menu.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_scrolling_header.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_meta.dart';
import 'package:omi/pages/conversation_detail/page.dart' show detailFloatingBarBottom, detailFloatingBarHeight;
import 'package:omi/pages/conversation_detail/widgets/earlier_voice_matches_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_chip.dart';
import 'package:omi/pages/conversation_detail/widgets/edit_segment_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_labeling_session_bar.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_quick_picker.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_summary_action.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_tag_outcome.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/services/experiments/experimental_design.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/audio/conversation_playback_controller.dart';
import 'package:omi/utils/constants.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/utils/reliability_experiments.dart';
import 'package:omi/widgets/expandable_text.dart';
import 'package:omi/widgets/transcript.dart';
import 'package:omi/widgets/speaker_label.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/pages/review/widgets/review_question_card.dart';
import 'package:omi/providers/review_provider.dart';

/// The conversation detail's Transcript tab: the speaker-summary action, then the transcript (or
/// the imported text of an external conversation), with segment editing and speaker naming.
class TranscriptWidgets extends StatefulWidget {
  final String searchQuery;
  final int currentResultIndex;
  final VoidCallback? onTapWhenSearchEmpty;
  final Function(TranscriptSegment)? onSegmentTap;
  final ConversationPlaybackController? playbackController;
  final Widget? Function(ServerConversation, Widget?)? livePreviewTail;

  const TranscriptWidgets({
    super.key,
    this.searchQuery = '',
    this.currentResultIndex = -1,
    this.onTapWhenSearchEmpty,
    this.onSegmentTap,
    this.playbackController,
    this.livePreviewTail,
  });

  @override
  State<TranscriptWidgets> createState() => _TranscriptWidgetsState();
}

class _TranscriptWidgetsState extends State<TranscriptWidgets> with AutomaticKeepAliveClientMixin {
  @override
  bool get wantKeepAlive => true;

  /// Follows a tag to its outcome (voice learned or not). Tests and the visual audit provide one
  /// seeded with fake fetchers; the app creates its own.
  SpeakerTagOutcomeController? _ownOutcome;
  late final SpeakerTagOutcomeController _outcome =
      context.read<SpeakerTagOutcomeController?>() ?? (_ownOutcome = SpeakerTagOutcomeController());

  /// Lines chosen to name together; null outside selection mode.
  Set<String>? _selection;

  /// Height of the fade the conversation page paints above its floating bar.
  static const double _barFade = 28;

  /// The last person tagged during a labeling pass. Its outcome card waits for Done instead of
  /// interrupting every label.
  ({String personId, String personName, int linesLabeled})? _deferredOutcome;

  @override
  void dispose() {
    _ownOutcome?.dispose();
    super.dispose();
  }

  /// [first] is the line the reader held to get here: it starts out chosen.
  void _beginSelection(ConversationDetailProvider provider, {String? first}) async {
    final id = provider.conversation.id;
    await provider.loadRecordingTranscript();
    if (!mounted || provider.conversationOrNull?.id != id) return;
    if (provider.recordingLoadFailed) {
      OmiFeedback.error(context,
          provider.recordingLoadLimited ? context.l10n.speakerRenameIssue('limit') : context.l10n.transcriptLoadFailed);
      return;
    }
    if (!_readyForTranscriptEdit(provider)) return;
    provider.beginSpeakerLabelingSession();
    setState(() => _selection = {if (first != null) first});
  }

  /// Experimental design: holding a line offers to choose lines or to name the line's speaker.
  Future<void> _openLineMenu(
    ConversationDetailProvider provider,
    TranscriptSegment segment,
    Offset at,
    Rect lineRect, {
    required bool canName,
    required String speakerName,
  }) async {
    final l10n = context.l10n;
    final actions = <(Key, String, IconData, VoidCallback)>[
      (
        const Key('transcript_line_menu_select'),
        l10n.selectOption,
        Icons.checklist,
        () => _beginSelection(provider, first: segment.id),
      ),
      if (canName)
        (
          const Key('transcript_line_menu_name'),
          l10n.nameSpeakerTitle,
          Icons.person_outline,
          () => _nameSpeaker(provider, segment.id, segment.speakerId),
        ),
      // Holding a line no longer selects its words, so the menu copies them.
      (
        const Key('transcript_line_menu_copy'),
        l10n.copy,
        Icons.copy_outlined,
        () async {
          if (mounted) await OmiClipboard.copy(context, segment.text.decodeString);
        },
      ),
    ];
    // Each platform's own menu: Material's on Android; on iPhone the page blurs and the line lifts
    // with its actions under it; the blurred pull-down elsewhere.
    if (Theme.of(context).platform == TargetPlatform.iOS) {
      await showTranscriptLineMenu(
        context,
        lineRect: lineRect,
        preview: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisSize: MainAxisSize.min,
          children: [
            if (speakerName.isNotEmpty) ...[
              Text(
                speakerName,
                style: OmiType.footnote.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: 3),
            ],
            Text(segment.text.decodeString, style: OmiType.body.copyWith(height: 1.5)),
          ],
        ),
        actions: [
          for (final (key, title, _, action) in actions)
            // Outline glyphs with a thinner stroke than Material's, which has one weight only.
            (key: key, title: title, icon: _thinIcon(key), onTap: action),
        ],
      );
      return;
    }
    if (Theme.of(context).platform == TargetPlatform.android) {
      final screen = MediaQuery.sizeOf(context);
      final chosen = await showMenu<VoidCallback>(
        context: context,
        position: RelativeRect.fromLTRB(at.dx, at.dy, screen.width - at.dx, screen.height - at.dy),
        items: [
          for (final (key, title, icon, action) in actions)
            PopupMenuItem<VoidCallback>(
              key: key,
              value: action,
              child: Row(children: [Icon(icon, size: 20), const SizedBox(width: OmiSpacing.sm), Text(title)]),
            ),
        ],
      );
      chosen?.call();
      return;
    }
    await showPullDownMenu(
      context: context,
      position: Rect.fromCenter(center: at, width: 1, height: 1),
      items: [
        for (final (key, title, icon, action) in actions)
          PullDownMenuItem(key: key, title: title, icon: icon, onTap: action),
      ],
    );
  }

  /// The name the transcript shows for [segment]'s speaker.
  String _speakerNameFor(
      ConversationDetailProvider provider, List<TranscriptSegment> segments, TranscriptSegment segment) {
    final people = context.read<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople;
    return SpeakerNames.forSegments(
      segments,
      people: people,
      l10n: context.l10n,
      unresolved: provider.conversation.speakerResolution?.status == 'unavailable',
    ).forSegment(segment, person: personById(people, segment.personId));
  }

  static FaIconData _thinIcon(Key key) {
    if (key == const Key('transcript_line_menu_select')) return FontAwesomeIcons.circleCheck;
    if (key == const Key('transcript_line_menu_name')) return FontAwesomeIcons.user;
    return FontAwesomeIcons.copy;
  }

  void _toggleSelection(TranscriptSegment segment) {
    final selection = _selection;
    if (selection == null) return;
    setState(() {
      if (!selection.remove(segment.id)) selection.add(segment.id);
    });
  }

  void _assignSelection(ConversationDetailProvider provider) {
    final selection = _selection;
    if (selection == null || selection.isEmpty || !_readyForTranscriptEdit(provider)) return;
    final conversation = provider.conversation;
    final lines = provider.recordingSegments.where((s) => selection.contains(s.id)).toList();
    if (lines.isEmpty) return;
    showSpeakerQuickPicker(
      context,
      segments: provider.recordingSegments,
      onPicked: (personId, personName) {
        final assigned = _startSpeakerAssignment(
          provider,
          conversation.id,
          lines.first.speakerId,
          personId,
          personName,
          [for (final line in lines) line.id],
          false,
        );
        if (assigned && mounted) setState(() => _selection = null);
        return assigned;
      },
    );
  }

  /// Done: one summary update for the whole pass, then the outcome of the last tag.
  void _finishLabeling(ConversationDetailProvider provider) {
    OmiHaptics.light();
    setState(() => _selection = null);
    provider.confirmSpeakerLabelingSession();
    final deferred = _deferredOutcome;
    _deferredOutcome = null;
    if (deferred != null) {
      _outcome.follow(
        personId: deferred.personId,
        personName: deferred.personName,
        linesLabeled: deferred.linesLabeled,
      );
    }
  }

  Future<void> _undoLabel(ConversationDetailProvider provider) async {
    OmiHaptics.light();
    final undone = await provider.undoLastSpeakerLabel();
    if (!undone && mounted) OmiFeedback.error(context, context.l10n.failedToSaveCheckConnection);
  }

  void _dismissSearchIfEmpty() {
    FocusScope.of(context).unfocus();
    if (widget.searchQuery.isEmpty) widget.onTapWhenSearchEmpty?.call();
  }

  bool _requireConnection() {
    if (Provider.of<ConnectivityProvider>(context, listen: false).isConnected) return true;
    ConnectivityProvider.showNoInternetDialog(context);
    return false;
  }

  bool _readyForTranscriptEdit(ConversationDetailProvider provider) => _requireConnection();

  /// What an empty Transcript tab says while its lines may still come: loading, couldn't load
  /// (Try Again), or being processed. Null when the conversation really has no transcript, or
  /// carries imported text instead, which the caller shows.
  Widget? _pendingTranscriptState(
    BuildContext context,
    ConversationDetailProvider provider,
    ServerConversation conversation,
  ) {
    if ((conversation.externalIntegration?.text ?? '').trim().isNotEmpty) return null;
    final l10n = context.l10n;
    final Widget state;
    if (provider.detailLoad == ConversationDetailLoad.loading) {
      state = OmiLoadingState(key: const Key('transcript_loading'), label: l10n.loadingTranscript);
    } else if (provider.detailLoad == ConversationDetailLoad.failed) {
      state = OmiErrorState(
        key: const Key('transcript_load_failed'),
        message: l10n.transcriptLoadFailed,
        onRetry: () => provider.refreshConversation(trackLoad: true),
      );
    } else if (conversation.status == ConversationStatus.processing ||
        conversation.status == ConversationStatus.in_progress ||
        provider.isReprocessingOpenConversation) {
      state = OmiLoadingState(key: const Key('transcript_processing'), label: l10n.processingConversationProgress);
    } else if (conversation.status == ConversationStatus.failed) {
      state = OmiErrorState(
        key: const Key('transcript_processing_failed'),
        message: l10n.conversationProcessingFailedMessage,
        onRetry: provider.loadingReprocessConversation ? null : () => provider.reprocessConversation(),
      );
    } else {
      state = OmiEmptyState(
        key: const Key('transcript_empty'),
        icon: Icons.notes,
        title: l10n.noTranscriptAvailable,
        message: l10n.noTranscriptMessage,
      );
    }
    return Padding(
      padding: const EdgeInsets.only(top: OmiSpacing.xxl),
      child: state,
    );
  }

  void _editSegmentText(ConversationDetailProvider provider, int segmentIndex) {
    if (!_readyForTranscriptEdit(provider)) return;
    final segments = provider.conversation.transcriptSegments;
    final segment = segments[segmentIndex];
    final people = context.read<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople;
    final speakerName = SpeakerNames.forSegments(
      segments,
      people: people,
      l10n: context.l10n,
      unresolved: provider.conversation.speakerResolution?.status == 'unavailable',
    ).forSegment(segment);
    PlatformManager.instance.analytics.editSegmentTextStarted();
    bool saved = false;
    showEditSegmentBottomSheet(
      context,
      segment: segment,
      speakerName: speakerName,
      onSave: (newText) {
        saved = true;
        PlatformManager.instance.analytics.editSegmentTextSaved();
        provider.saveEditingSegmentText(segmentIndex, newText);
      },
      onDismissed: () {
        if (!saved) PlatformManager.instance.analytics.editSegmentTextCancelled();
      },
    );
  }

  void _nameSpeaker(ConversationDetailProvider provider, String segmentId, int speakerId) {
    speakerId = provider.sourceSpeakerId(segmentId, speakerId);
    if (!_readyForTranscriptEdit(provider)) return;
    showNameSpeakerSheet(
      context,
      speakerId: speakerId,
      segmentId: segmentId,
      segments: provider.voiceSegmentsFor(segmentId, speakerId),
      wholeRecording: true,
      recordingCoverageComplete: () =>
          provider.recordingCoverageComplete && provider.recordingVoiceFor(segmentId) != null,
      loadRecordingLines: () async {
        await provider.loadRecordingTranscript();
        return provider.voiceSegmentsFor(segmentId, speakerId);
      },
      unresolvedSpeakers: provider.conversation.speakerResolution?.status == 'unavailable',
      // The name heads a turn; naming it names that voice's lines, which the sheet lists to uncheck.
      defaultApplyToSpeaker: true,
      onSpeakerAssigned: (speakerId, personId, personName, segmentIds, applyToSpeaker) async {
        return _startSpeakerAssignment(
          provider,
          provider.conversation.id,
          speakerId,
          personId,
          personName,
          segmentIds,
          applyToSpeaker,
        );
      },
      onSpeakerRejected: (kind) async {
        final segment = provider.conversation.transcriptSegments.where((s) => s.id == segmentId).firstOrNull;
        return segment != null && await provider.rejectSpeakerLabel(segment, kind);
      },
    );
  }

  /// "Yes" under a line Omi named by voice: the user's answer for every line from that voice.
  void _confirmSpeakerLabel(ConversationDetailProvider provider, TranscriptSegment segment) {
    final personId = segment.personId;
    if (personId == null || !_readyForTranscriptEdit(provider)) return;
    final name = context.read<PeopleProvider>().people.where((p) => p.id == personId).firstOrNull?.name ?? '';
    OmiHaptics.light();
    _startSpeakerAssignment(provider, provider.conversation.id, provider.sourceSpeakerId(segment.id, segment.speakerId),
        personId, name, [segment.id], true);
  }

  /// "Not <name>": clears that label from the voice and tells Omi not to match it that way again.
  Future<void> _rejectSpeakerLabel(ConversationDetailProvider provider, TranscriptSegment segment) async {
    if (!_readyForTranscriptEdit(provider)) return;
    OmiHaptics.light();
    final rejected = await provider.rejectSpeakerLabel(segment, SpeakerRejection.notPerson);
    if (!mounted) return;
    rejected
        ? OmiFeedback.confirm(context, context.l10n.speakerTagPromptRejectedToast)
        : OmiFeedback.error(context, context.l10n.failedToSaveCheckConnection);
  }

  void _reviewEarlierMatches(SpeakerTagOutcome outcome) {
    showEarlierVoiceMatchesSheet(
      context,
      personName: outcome.personName,
      matches: outcome.matches,
      onAnswer: (match, same) async {
        final saved = same
            ? await assignBulkConversationTranscriptSegments(
                match.conversationId,
                match.segmentIds,
                personId: outcome.personId,
                speakerId: match.speakerId,
              )
            : await rejectConversationSpeaker(
                match.conversationId,
                match.speakerId,
                SpeakerRejection.notPerson,
                personId: outcome.personId,
              ) is ApiSuccess<ServerConversation>;
        if (saved) _outcome.removeMatch(match);
        return saved;
      },
    );
  }

  bool _startSpeakerAssignment(
    ConversationDetailProvider provider,
    String conversationId,
    int speakerId,
    String personId,
    String personName,
    List<String> segmentIds,
    bool applyToSpeaker,
  ) {
    final peopleProvider = context.read<PeopleProvider>();
    if (provider.conversationOrNull?.id != conversationId) return false;
    // Every label joins a labeling pass, so the summary updates once at Done, not after each pause.
    provider.beginSpeakerLabelingSession();
    final newPerson = personId.isEmpty;
    final temporaryId = newPerson ? 'optimistic-person:${DateTime.now().microsecondsSinceEpoch}' : null;
    if (temporaryId != null) {
      peopleProvider.addOptimisticPerson(
        Person(id: temporaryId, name: personName, createdAt: DateTime.now(), updatedAt: DateTime.now()),
      );
    }
    var resolvedId = personId;
    final pending = provider.startSpeakerAssignment(
      segmentIds,
      temporaryId ?? personId,
      speakerId: applyToSpeaker ? speakerId : null,
      expectedConversationId: conversationId,
      createPerson: newPerson ? () async => (await peopleProvider.createPersonProvider(personName))?.id : null,
      onReconciled: (id) {
        resolvedId = id;
        if (temporaryId != null) peopleProvider.removeOptimisticPerson(temporaryId);
      },
      onFailed: () {
        if (temporaryId != null) peopleProvider.removeOptimisticPerson(temporaryId);
        if (!mounted) return;
        if (provider.speakerAssignmentLimited || provider.speakerAssignmentPartial) {
          OmiFeedback.error(
              context, context.l10n.speakerRenameIssue(provider.speakerAssignmentLimited ? 'limit' : 'partial'));
          return;
        }
        if (provider.speakerAssignmentStale) {
          OmiFeedback.error(context, context.l10n.speakerSelectionChanged);
          unawaited(provider.refreshConversation());
          return;
        }
        OmiFeedback.error(
          context,
          provider.speakerAssignmentStale
              ? context.l10n.speakerSelectionChanged
              : context.l10n.failedToSaveCheckConnection,
          actionLabel: context.l10n.retry,
          onAction: () => _startSpeakerAssignment(
            provider,
            conversationId,
            speakerId,
            resolvedId,
            personName,
            segmentIds,
            applyToSpeaker,
          ),
        );
      },
    );
    if (pending == null) {
      if (temporaryId != null) peopleProvider.removeOptimisticPerson(temporaryId);
      return false;
    }
    final linesLabeled = applyToSpeaker
        ? provider.conversation.transcriptSegments.where((s) => s.speakerId == speakerId).length
        : segmentIds.length;
    unawaited(
      pending.then((saved) {
        if (temporaryId != null) peopleProvider.removeOptimisticPerson(temporaryId);
        if (saved) {
          if (mounted &&
              (!provider.speakerCoverageComplete ||
                  !provider.speakerLabelingSessionActive ||
                  provider.lastSpeakerAppliedCount != linesLabeled)) {
            OmiFeedback.confirm(
                context,
                provider.speakerCoverageComplete
                    ? context.l10n.speakerLabelLinesLabeled(provider.lastSpeakerAppliedCount)
                    : context.l10n.speakerRecordingCoverage('saved', provider.lastSpeakerAppliedCount));
          }
          PlatformManager.instance.analytics.taggedSegment(resolvedId == 'user' ? 'User' : 'User Person');
          if (mounted && resolvedId != 'user' && provider.conversationOrNull?.id == conversationId) {
            if (provider.speakerLabelingSessionActive) {
              _deferredOutcome = (personId: resolvedId, personName: personName, linesLabeled: linesLabeled);
            } else {
              _outcome.follow(personId: resolvedId, personName: personName, linesLabeled: linesLabeled);
            }
          }
        }
      }),
    );
    return true;
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    return Listener(
      onPointerDown: (_) => _dismissSearchIfEmpty(),
      child: GestureDetector(
        excludeFromSemantics: true,
        behavior: HitTestBehavior.translucent,
        onTap: _dismissSearchIfEmpty,
        child: Consumer<ConversationDetailProvider>(
          builder: (context, provider, child) {
            final conversation = provider.conversation;
            final segments = conversation.transcriptSegments;
            final photos = conversation.photos;

            Widget? empty;
            if (segments.isEmpty && photos.isEmpty) {
              empty = _pendingTranscriptState(context, provider, conversation) ??
                  Padding(
                    padding: const EdgeInsets.only(top: OmiSpacing.xxl),
                    child: ExpandableTextWidget(
                      text: (conversation.externalIntegration?.text ?? '').decodeString,
                      maxLines: 1000,
                      linkColor: OmiColors.textSecondary,
                      style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.3),
                      toggleExpand: provider.toggleIsTranscriptExpanded,
                      isExpanded: provider.isTranscriptExpanded,
                    ),
                  );
            }
            final tail = widget.livePreviewTail?.call(conversation, empty);
            // No list of its own: the page's header stays where it is.
            if (tail == null && empty != null) return ConversationScrollingHeaderPinned(child: empty);

            final selection = _selection;
            // A bar pinned above the lines holds the page's header in place too; otherwise the
            // header scrolls away with the lines (experimental design).
            return ListenableBuilder(
              listenable: _outcome,
              builder: (context, _) {
                final barPinned = provider.speakerLabelingSessionActive ||
                    selection != null ||
                    _outcome.outcome != null ||
                    provider.offerSpeakerSummaryRefresh;
                return ConversationScrollingHeaderPinned(
                  pinned: barPinned,
                  child: Column(
                    children: [
                      SpeakerSummaryAction(provider: provider),
                      if (provider.speakerLabelingSessionActive || selection != null)
                        SpeakerLabelingSessionBar(
                          linesRelabeled: provider.speakerLabelingSessionLineCount,
                          selectedCount: selection?.length,
                          onDone: () => _finishLabeling(provider),
                          onSelect: () => _beginSelection(provider),
                          onCancelSelection: () => setState(() => _selection = null),
                          onAssign: () => _assignSelection(provider),
                          onUndo: provider.canUndoSpeakerLabel ? () => _undoLabel(provider) : null,
                        ),
                      ListenableBuilder(
                        listenable: _outcome,
                        builder: (context, _) {
                          final outcome = _outcome.outcome;
                          if (outcome == null) return const SizedBox.shrink();
                          return SpeakerTagOutcomeCard(
                            outcome: outcome,
                            onClose: _outcome.dismiss,
                            onReview: () => _reviewEarlierMatches(outcome),
                          );
                        },
                      ),
                      Expanded(
                        child: widget.playbackController == null
                            ? _buildTranscript(null, tail, headerInset: !barPinned)
                            : _PlaybackFollowScope(
                                controller: widget.playbackController!,
                                builder: (context) =>
                                    _buildTranscript(widget.playbackController, tail, headerInset: !barPinned),
                              ),
                      ),
                    ],
                  ),
                );
              },
            );
          },
        ),
      ),
    );
  }

  Widget _buildTranscript(ConversationPlaybackController? controller, Widget? tail, {bool headerInset = false}) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        final conversation = provider.conversation;
        final segments = provider.recordingDisplaySegments;
        final photos = conversation.photos;
        final playback = provider.hasRecordingSiblings ? null : controller;
        // Follow while the reader hasn't taken the scroll back AND playback
        // is either running or a fresh explicit request (line tap, scrub,
        // Play, back-to-current) asks for it — an idle first open does not.
        final followPlayback =
            playback != null && playback.isFollowing && (playback.isPlaying || playback.followRequest > 0);
        // A conversation still in progress keeps its newest line in view, the stored lines and the
        // live ones under them alike, until the reader scrolls away. Playing a line and choosing lines
        // hold the reader's place instead.
        final live = context.select<ConversationsV3Provider?, bool>((v3) => v3?.v3 ?? false) &&
            conversation.v3?.tileState == ConversationTileState.live;
        final followLatest = live && !followPlayback && _selection == null;
        // What the page's floating bar and the fade above it cover at the foot of the list.
        final barReach =
            detailFloatingBarBottom(MediaQuery.viewPaddingOf(context).bottom) + detailFloatingBarHeight + _barFade;
        // Review's "Who said this?" for this conversation sits above the lines it asks about.
        final reviewQuestion = context.watch<ReviewProvider?>()?.speakerQuestionIn(conversation.id);
        playback?.updateSegments(segments);
        // Each leading row carries its own id so the two lists TranscriptWidget needs can't drift apart.
        final experimental = ExperimentalDesign.of(context);
        final onDevice = segments.any((s) => s.sttProvider?.startsWith('on_device:') == true);
        // Room for the page's header when it scrolls with these lines (experimental design).
        final inset = headerInset ? ConversationScrollingHeader.insetOf(context) : 0.0;
        final leading = <(String, Widget)>[
          if (inset > 0) ('page-header-inset', SizedBox(height: inset)),
          if (provider.isReprocessingOpenConversation || provider.loadingRecordingTranscript)
            (
              'speaker-summary-updating',
              const Padding(
                  padding: EdgeInsets.only(bottom: OmiSpacing.sm), child: OmiSpinner(size: OmiSpinnerSize.small)),
            ),
          if (segments.isNotEmpty)
            (
              'transcript-heading',
              _TranscriptHeading(
                conversation: conversation,
                segments: segments,
                holdHint: experimental,
                onSelect: provider.speakerLabelingSessionActive || _selection != null
                    ? null
                    : () => _beginSelection(provider),
              ),
            ),
          if (segments.isNotEmpty && reviewQuestion != null)
            (
              'review-question-${reviewQuestion.itemId}',
              ReviewQuestionCard(item: reviewQuestion, margin: const EdgeInsets.only(bottom: OmiSpacing.md)),
            ),
        ];
        return getTranscriptWidget(
          false,
          segments,
          photos,
          null,
          conversationId: conversation.id,
          horizontalMargin: false,
          topMargin: false,
          canDisplaySeconds: provider.canDisplaySeconds,
          isConversationDetail: true,
          unresolvedSpeakers: conversation.speakerResolution?.status == 'unavailable',
          // A saved conversation ends with room to spare. One still in progress is read at its end,
          // so its newest line sits just above the bar instead of a third of the way up the screen.
          bottomMargin:
              live ? (barReach + OmiSpacing.lg - TranscriptWidget.footerHeight).clamp(0.0, 150.0).toDouble() : 150,
          searchQuery: widget.searchQuery,
          currentResultIndex: widget.currentResultIndex,
          onTapWhenSearchEmpty: widget.onTapWhenSearchEmpty,
          // Reliability experiment no_live_player: with no player on the page a line tap seeks nothing.
          onSegmentTap: widget.onSegmentTap == null || (live && ReliabilityExperiments.enabled('no_live_player'))
              ? null
              : (TranscriptSegment segment) {
                  final local = conversation.transcriptSegments.where((line) => line.id == segment.id).firstOrNull;
                  if (local != null) widget.onSegmentTap?.call(local);
                },
          onEditSegmentText: (segmentIndex) {
            final local = conversation.transcriptSegments.indexWhere((line) => line.id == segments[segmentIndex].id);
            if (local >= 0) _editSegmentText(provider, local);
          },
          editSegment: onDevice ? null : (segmentId, speakerId) => _nameSpeaker(provider, segmentId, speakerId),
          onConfirmSpeakerLabel: (segment) => _confirmSpeakerLabel(provider, segment),
          onRejectSpeakerLabel: (segment) => _rejectSpeakerLabel(provider, segment),
          startedAt: conversation.startedAt ?? conversation.createdAt,
          leadingItems: [for (final item in leading) item.$2],
          leadingItemIds: [for (final item in leading) item.$1],
          contentVersion: identityHashCode(segments),
          trailingItem: tail,
          currentSegmentId: playback?.currentSegmentId,
          highlightedSegment: playback?.highlightedSegment,
          followTargetSegmentId: playback?.followTargetSegmentId,
          followCurrentSegment: followPlayback,
          followLatest: followLatest,
          // Above the page's floating bar and the fade the page paints over the lines behind it.
          jumpToLatestButtonBottom: barReach + OmiSpacing.xs,
          playbackFollowRequest: playback?.followRequest ?? 0,
          onUserScroll: playback?.suspendFollowing,
          onTopVisibleSegmentChanged: playback?.readerMovedTo,
          selectedSegmentIds: _selection,
          onToggleSegmentSelection: _toggleSelection,
          onSegmentLongPress: !experimental || _selection != null
              ? null
              : (segment, at, lineRect) => _openLineMenu(
                    provider,
                    segment,
                    at,
                    lineRect,
                    canName: !onDevice && (segment.isUser || segment.speakerId != omiSpeakerId),
                    speakerName: _speakerNameFor(provider, segments, segment),
                  ),
        );
      },
    );
  }
}

/// "Transcript · 2 speakers" over the lines (Omi v8 transcript heading): how many voices took part,
/// counting the owner once. The length is in the header's date chip, so it is not repeated here.
class _TranscriptHeading extends StatelessWidget {
  const _TranscriptHeading({required this.conversation, this.segments, this.onSelect, this.holdHint = false});

  /// Experimental design: no heading chip and no Select button (the tab already says Transcript, and
  /// holding a line offers Select); a line of text says how to name speakers instead.
  final bool holdHint;

  final ServerConversation conversation;
  final List<TranscriptSegment>? segments;

  /// "Select": choose several lines and name their speaker at once. Null hides it (already labeling).
  final VoidCallback? onSelect;

  /// Missing or uncountable resolution omits the count, matching the header chip's uncounted
  /// "others" rule.
  static int? _speakerCount(
      ServerConversation conversation, List<Person> people, String you, List<TranscriptSegment> segments) {
    if (segments.any((s) => s.sttProvider?.startsWith('on_device:') == true)) return null;
    final participants = ConversationDetailMeta.participants(segments,
        you: you, personName: (id) => personById(people, id)?.name, speakers: conversation.speakerResolution);
    if (participants.uncounted) return null;
    final count = participants.named.length + participants.unnamed;
    return count == 0 ? null : count;
  }

  static bool _hasUnnamedVoice(ServerConversation conversation, List<Person> people) {
    if (conversation.speakerResolution?.status != 'unavailable') return false;
    return conversation.transcriptSegments.any((segment) {
      if (segment.isUser || segment.speakerId == omiSpeakerId) return false;
      final person = personById(people, segment.personId);
      return person == null || person.name.trim().isEmpty;
    });
  }

  static void _explainUnresolved(BuildContext context) => showOmiSheet<void>(
        context: context,
        title: context.l10n.unresolvedSpeakersTitle,
        builder: (sheetContext) => SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.only(bottom: OmiSpacing.md),
            child: Text(
              sheetContext.l10n.unresolvedSpeakersMessage,
              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
            ),
          ),
        ),
      );

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final people = context.watch<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople;
    final count = _speakerCount(conversation, people, l10n.you, segments ?? conversation.transcriptSegments);
    final label = [l10n.transcript, if (count != null) l10n.transcriptSpeakerCount(count)].join(' · ');
    if (holdHint) {
      final note = OmiType.footnote.copyWith(color: OmiColors.textSecondary);
      final unresolved = _hasUnnamedVoice(conversation, people);
      final hint = Text(
        unresolved ? '${l10n.unresolvedSpeakersNotice} ${l10n.transcriptHoldLineHint}' : l10n.transcriptHoldLineHint,
        key: const Key('transcript_hold_line_hint'),
        style: note,
      );
      return Padding(
        padding: const EdgeInsets.only(top: 14, bottom: 14),
        child: unresolved
            ? InkWell(
                key: const Key('transcript_unresolved_speakers_notice'),
                onTap: () => _explainUnresolved(context),
                child: hint,
              )
            : hint,
      );
    }
    return Padding(
      padding: const EdgeInsets.only(top: 18, bottom: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Wrap(
            spacing: OmiSpacing.sm,
            runSpacing: OmiSpacing.xs,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              ConversationDetailChip(
                key: const Key('conversation_transcript_heading'),
                icon: const Icon(Icons.notes),
                label: label,
                maxLines: null,
              ),
              if (onSelect != null)
                OmiButton(
                  key: const Key('transcript_select_lines'),
                  variant: OmiButtonVariant.tertiary,
                  label: "${l10n.selectOption} · ${l10n.transcript}",
                  icon: Icons.checklist,
                  size: OmiButtonSize.compact,
                  maxLines: null,
                  onPressed: onSelect,
                ),
            ],
          ),
          if (_hasUnnamedVoice(conversation, people))
            InkWell(
              key: const Key('transcript_unresolved_speakers_notice'),
              onTap: () => _explainUnresolved(context),
              child: ConstrainedBox(
                constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
                child: Align(
                  alignment: AlignmentDirectional.centerStart,
                  child: Text(
                    l10n.unresolvedSpeakersNotice,
                    style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
                  ),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

/// Rebuilds the transcript when playback follow changes, and not when a reader
/// scroll only moves the highlighted line. That highlight is [ConversationPlaybackController.highlightedSegment].
class _PlaybackFollowScope extends StatefulWidget {
  const _PlaybackFollowScope({required this.controller, required this.builder});

  final ConversationPlaybackController controller;
  final WidgetBuilder builder;

  @override
  State<_PlaybackFollowScope> createState() => _PlaybackFollowScopeState();
}

class _PlaybackFollowScopeState extends State<_PlaybackFollowScope> {
  late bool _playing;
  late bool _following;
  late int _followRequest;
  late String? _followTarget;

  @override
  void initState() {
    super.initState();
    _capture();
    widget.controller.addListener(_onController);
  }

  @override
  void didUpdateWidget(_PlaybackFollowScope oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.controller != widget.controller) {
      oldWidget.controller.removeListener(_onController);
      _capture();
      widget.controller.addListener(_onController);
    }
  }

  @override
  void dispose() {
    widget.controller.removeListener(_onController);
    super.dispose();
  }

  void _capture() {
    final controller = widget.controller;
    _playing = controller.isPlaying;
    _following = controller.isFollowing;
    _followRequest = controller.followRequest;
    _followTarget = controller.followTargetSegmentId;
  }

  void _onController() {
    if (!mounted) return;
    final controller = widget.controller;
    final followActive = controller.isFollowing && (controller.isPlaying || controller.followRequest > 0);
    final transportChanged = controller.isPlaying != _playing ||
        controller.isFollowing != _following ||
        controller.followRequest != _followRequest;
    final targetChanged = followActive && controller.followTargetSegmentId != _followTarget;
    if (!transportChanged && !targetChanged) return;
    setState(_capture);
  }

  @override
  Widget build(BuildContext context) => widget.builder(context);
}
