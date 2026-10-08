import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart' show assignBulkConversationTranscriptSegments;
import 'package:omi/backend/http/api/speaker_labels.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/mobile/native_ui/ios_native_surface.dart';
import 'package:omi/pages/capture/widgets/widgets.dart';
import 'package:omi/pages/conversation_detail/conversation_detail_provider.dart';
import 'package:omi/pages/conversation_detail/widgets/earlier_voice_matches_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_chip.dart';
import 'package:omi/pages/conversation_detail/widgets/edit_segment_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/name_speaker_sheet.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_summary_action.dart';
import 'package:omi/pages/conversation_detail/widgets/speaker_tag_outcome.dart';
import 'package:omi/providers/connectivity_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/audio/conversation_playback_controller.dart';
import 'package:omi/utils/constants.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/expandable_text.dart';
import 'package:omi/widgets/speaker_label.dart';
import 'package:omi/widgets/speaker_label_badge.dart';
import 'package:omi/widgets/extensions/string.dart';
import 'package:omi/widgets/media_viewer_page.dart';
import 'package:omi/widgets/photos_grid.dart';

/// The conversation detail's Transcript tab: the speaker-summary action, then the transcript (or
/// the imported text of an external conversation), with segment editing and speaker naming.
class TranscriptWidgets extends StatefulWidget {
  final String searchQuery;
  final int currentResultIndex;
  final VoidCallback? onTapWhenSearchEmpty;
  final Function(TranscriptSegment)? onSegmentTap;
  final ConversationPlaybackController? playbackController;
  final ValueChanged<List<NativeSection>>? onNativePresentation;

  const TranscriptWidgets({
    super.key,
    this.searchQuery = '',
    this.currentResultIndex = -1,
    this.onTapWhenSearchEmpty,
    this.onSegmentTap,
    this.playbackController,
    this.onNativePresentation,
  });

  @override
  State<TranscriptWidgets> createState() => _TranscriptWidgetsState();
}

class _TranscriptWidgetsState extends State<TranscriptWidgets> with AutomaticKeepAliveClientMixin {
  bool _nativeScheduled = false;
  bool _nativeObserving = false;
  @override
  bool get wantKeepAlive => true;

  /// Follows a tag to its outcome (voice learned or not). Tests and the visual audit provide one
  /// seeded with fake fetchers; the app creates its own.
  SpeakerTagOutcomeController? _ownOutcome;
  late final SpeakerTagOutcomeController _outcome =
      context.read<SpeakerTagOutcomeController?>() ?? (_ownOutcome = SpeakerTagOutcomeController());

  @override
  void didChangeDependencies() {
    super.didChangeDependencies();
    if (widget.onNativePresentation != null && !_nativeObserving) {
      _nativeObserving = true;
      _outcome.addListener(_publishNativePresentation);
    }
  }

  @override
  void dispose() {
    if (_nativeObserving) _outcome.removeListener(_publishNativePresentation);
    _ownOutcome?.dispose();
    super.dispose();
  }

  // Presentation only: commands call the same edit/attribution owners below. Resolve a
  // segment by its server id at dispatch time so a refreshed transcript cannot edit a neighbour.
  void _publishNativePresentation() {
    if (widget.onNativePresentation == null || _nativeScheduled) return;
    _nativeScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _nativeScheduled = false;
      if (!mounted || widget.onNativePresentation == null) return;
      final provider = context.read<ConversationDetailProvider>();
      final conversation = provider.conversation;
      final segments = conversation.transcriptSegments;
      final l10n = context.l10n;
      final names = SpeakerNames.forSegments(segments,
          people: context.read<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople,
          l10n: l10n,
          unresolved: conversation.speakerResolution?.status == 'unavailable');
      widget.playbackController?.updateSegments(segments);
      final rows = <NativeRow>[];
      if (provider.offerSpeakerSummaryRefresh) {
        rows.add(NativeRow('detail_speaker_summary', l10n.updateSummaryWithNewNames,
            enabled: !provider.loadingReprocessConversation,
            symbol: 'arrow.clockwise',
            action: (_) => provider.reprocessConversation()));
      }
      final outcome = _outcome.outcome;
      if (outcome != null) {
        rows.addAll([
          NativeRow('detail_speaker_outcome', l10n.speakerTagPromptLabeledToast(outcome.personName),
              kind: 'label',
              subtitle: '${l10n.speakerLabelLinesLabeled(outcome.linesLabeled)}\n'
                  '${l10n.speakerLabelVoiceStatus(outcome.voiceState)}\n'
                  '${l10n.speakerLabelVoiceDetail(outcome.voiceState, outcome.personName)}'),
          if (outcome.matches.isNotEmpty)
            NativeRow('detail_speaker_matches', l10n.speakerLabelText('other', ''),
                subtitle: l10n.speakerLabelEarlierMatches(outcome.matches.length),
                action: (_) => _reviewEarlierMatches(outcome)),
          NativeRow('detail_speaker_outcome_close', l10n.close, symbol: 'xmark', action: (_) => _outcome.dismiss()),
        ]);
      }
      if (segments.isEmpty && conversation.photos.isEmpty) {
        final external = (conversation.externalIntegration?.text ?? '').decodeString;
        final title = switch (provider.detailLoad) {
          ConversationDetailLoad.loading => l10n.loadingTranscript,
          ConversationDetailLoad.failed => l10n.transcriptLoadFailed,
          _ => external.isNotEmpty
              ? external
              : conversation.status == ConversationStatus.processing ||
                      conversation.status == ConversationStatus.in_progress ||
                      provider.isReprocessingOpenConversation
                  ? l10n.processingConversationProgress
                  : conversation.status == ConversationStatus.failed
                      ? l10n.conversationProcessingFailedMessage
                      : l10n.noTranscriptAvailable,
        };
        rows.add(NativeRow('detail_transcript_status', title, kind: 'label'));
        if (provider.detailLoad == ConversationDetailLoad.failed || conversation.status == ConversationStatus.failed) {
          rows.add(NativeRow('detail_transcript_retry', l10n.tryAgain,
              enabled: !provider.loadingReprocessConversation,
              action: (_) => provider.detailLoad == ConversationDetailLoad.failed
                  ? provider.refreshConversation(trackLoad: true)
                  : provider.reprocessConversation()));
        }
      }
      final autoLabelIds = firstAutoLabelSegmentIds(segments);
      for (final segment in segments) {
        rows.add(NativeRow('detail_segment:${segment.id}', segment.text,
            kind: 'transcript',
            subtitle: '${names.forSegment(segment)} · ${OmiDuration.offset(segment.start)}',
            options: {
              'edit': l10n.edit,
              'speaker': l10n.speakerLabelText('other', ''),
            }, action: (value) {
          if (provider.conversationOrNull?.id != conversation.id) return;
          final current = provider.conversation.transcriptSegments;
          final index = current.indexWhere((item) => item.id == segment.id);
          if (index < 0) return;
          final item = current[index];
          if (value == 'edit') {
            _editSegmentText(provider, index);
          } else if (value == 'speaker') {
            _nameSpeaker(provider, item.id, item.speakerId);
          } else {
            widget.onSegmentTap?.call(item);
          }
        }));
        if (autoLabelIds.contains(segment.id)) {
          rows.addAll([
            NativeRow('detail_speaker_confirm:${segment.id}', l10n.yes,
                action: (_) => _confirmSpeakerLabel(provider, segment)),
            NativeRow(
                'detail_speaker_reject:${segment.id}', l10n.speakerLabelText('notPerson', names.forSegment(segment)),
                action: (_) => _rejectSpeakerLabel(provider, segment)),
          ]);
        }
      }
      for (final photo in conversation.photos) {
        rows.add(NativeRow('detail_photo:${photo.id}', photo.description ?? l10n.photos, symbol: 'photo', action: (_) {
          final current = provider.conversationOrNull;
          if (current?.id != conversation.id) return;
          final index = current!.photos.indexWhere((candidate) => candidate.id == photo.id);
          if (index < 0) return;
          MediaViewerPage.open(context, items: mediaItemsForPhotos(current.photos, current.id), initialIndex: index);
        }));
      }
      widget.onNativePresentation!([NativeSection('detail_transcript', rows, title: l10n.transcript)]);
    });
    WidgetsBinding.instance.ensureVisualUpdate();
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

  /// Transcript and speaker edits wait while the conversation is being reprocessed (the reprocess replaces the
  /// lines they would change); say so instead of ignoring the tap.
  bool _readyForTranscriptEdit(ConversationDetailProvider provider) {
    if (!provider.loadingReprocessConversation) return _requireConnection();
    OmiFeedback.info(context, context.l10n.waitForReprocessing);
    return false;
  }

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
    final conversationId = provider.conversation.id;
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
        if (provider.conversationOrNull?.id != conversationId) return;
        final currentIndex = provider.conversation.transcriptSegments.indexWhere((line) => line.id == segment.id);
        if (currentIndex < 0) return;
        saved = true;
        PlatformManager.instance.analytics.editSegmentTextSaved();
        provider.saveEditingSegmentText(currentIndex, newText);
      },
      onDismissed: () {
        if (!saved) PlatformManager.instance.analytics.editSegmentTextCancelled();
      },
    );
  }

  void _nameSpeaker(ConversationDetailProvider provider, String segmentId, int speakerId) {
    if (!_readyForTranscriptEdit(provider)) return;
    final conversationId = provider.conversation.id;
    showNameSpeakerSheet(
      context,
      speakerId: speakerId,
      segmentId: segmentId,
      segments: provider.conversation.transcriptSegments,
      unresolvedSpeakers: provider.conversation.speakerResolution?.status == 'unavailable',
      onSpeakerAssigned: (speakerId, personId, personName, segmentIds, applyToSpeaker) async {
        return _startSpeakerAssignment(
          provider,
          conversationId,
          speakerId,
          personId,
          personName,
          segmentIds,
          applyToSpeaker,
        );
      },
      onSpeakerRejected: (kind) async {
        if (provider.conversationOrNull?.id != conversationId) return false;
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
    _startSpeakerAssignment(provider, provider.conversation.id, segment.speakerId, personId, name, [segment.id], true);
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
        OmiFeedback.error(
          context,
          context.l10n.failedToSaveCheckConnection,
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
          PlatformManager.instance.analytics.taggedSegment(resolvedId == 'user' ? 'User' : 'User Person');
          if (mounted && resolvedId != 'user' && provider.conversationOrNull?.id == conversationId) {
            _outcome.follow(personId: resolvedId, personName: personName, linesLabeled: linesLabeled);
          }
        }
      }),
    );
    return true;
  }

  @override
  Widget build(BuildContext context) {
    super.build(context);
    if (widget.onNativePresentation != null) context.watch<PeopleProvider?>();
    return Listener(
      onPointerDown: (_) => _dismissSearchIfEmpty(),
      child: GestureDetector(
        excludeFromSemantics: true,
        behavior: HitTestBehavior.translucent,
        onTap: _dismissSearchIfEmpty,
        child: Consumer<ConversationDetailProvider>(
          builder: (context, provider, child) {
            _publishNativePresentation();
            final conversation = provider.conversation;
            final segments = conversation.transcriptSegments;
            final photos = conversation.photos;

            if (segments.isEmpty && photos.isEmpty) {
              final pending = _pendingTranscriptState(context, provider, conversation);
              if (pending != null) return pending;
              return Padding(
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

            return Column(
              children: [
                SpeakerSummaryAction(provider: provider),
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
                      ? _buildTranscript(null)
                      : ListenableBuilder(
                          listenable: widget.playbackController!,
                          builder: (context, _) => _buildTranscript(widget.playbackController),
                        ),
                ),
              ],
            );
          },
        ),
      ),
    );
  }

  Widget _buildTranscript(ConversationPlaybackController? controller) {
    return Consumer<ConversationDetailProvider>(
      builder: (context, provider, child) {
        final conversation = provider.conversation;
        final segments = conversation.transcriptSegments;
        final photos = conversation.photos;
        controller?.updateSegments(segments);
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
          bottomMargin: 150,
          searchQuery: widget.searchQuery,
          currentResultIndex: widget.currentResultIndex,
          onTapWhenSearchEmpty: widget.onTapWhenSearchEmpty,
          onSegmentTap: widget.onSegmentTap,
          onEditSegmentText: (segmentIndex) => _editSegmentText(provider, segmentIndex),
          editSegment: (segmentId, speakerId) => _nameSpeaker(provider, segmentId, speakerId),
          onConfirmSpeakerLabel: (segment) => _confirmSpeakerLabel(provider, segment),
          onRejectSpeakerLabel: (segment) => _rejectSpeakerLabel(provider, segment),
          startedAt: conversation.startedAt ?? conversation.createdAt,
          leadingItems: [if (segments.isNotEmpty) _TranscriptHeading(conversation: conversation)],
          leadingItemIds: [if (segments.isNotEmpty) 'transcript-heading'],
          currentSegmentId: controller?.currentSegmentId,
          followTargetSegmentId: controller?.followTargetSegmentId,
          // Follow while the reader hasn't taken the scroll back AND playback
          // is either running or a fresh explicit request (line tap, scrub,
          // Play, back-to-current) asks for it — an idle first open does not.
          followCurrentSegment:
              controller != null && controller.isFollowing && (controller.isPlaying || controller.followRequest > 0),
          playbackFollowRequest: controller?.followRequest ?? 0,
          onUserScroll: controller?.suspendFollowing,
          onTopVisibleSegmentChanged: controller?.readerMovedTo,
        );
      },
    );
  }
}

/// "Transcript · 2 speakers" over the lines (Omi v8 transcript heading): how many voices took part,
/// counting the owner once. The length is in the header's date chip, so it is not repeated here.
class _TranscriptHeading extends StatelessWidget {
  const _TranscriptHeading({required this.conversation});

  final ServerConversation conversation;

  /// Missing or uncountable resolution omits the count, matching the header chip's uncounted
  /// "others" rule.
  static int? _speakerCount(ServerConversation conversation) {
    final resolution = conversation.speakerResolution;
    if (resolution == null || !resolution.countable) return null;
    final segments = conversation.transcriptSegments;
    final ownerIds = {
      for (final segment in segments)
        if (segment.isUser) segment.speakerId,
    };
    final personIdsBySpeaker = <int, Set<String>>{};
    for (final segment in segments) {
      if (segment.isUser || segment.speakerId == omiSpeakerId) continue;
      final personId = segment.personId;
      if (personId != null && personId.trim().isNotEmpty) {
        personIdsBySpeaker.putIfAbsent(segment.speakerId, () => {}).add(personId);
      }
    }
    final voices = <String>{};
    for (final rawId in resolution.participantSpeakerIds.toSet()) {
      if (ownerIds.contains(rawId) || rawId == omiSpeakerId) continue;
      final personIds = personIdsBySpeaker[rawId];
      if (personIds == null || personIds.isEmpty) {
        voices.add('speaker-$rawId');
      } else {
        voices.addAll(personIds.map((id) => 'person-$id'));
      }
    }
    return voices.length + (ownerIds.isEmpty ? 0 : 1);
  }

  static bool _hasUnnamedVoice(ServerConversation conversation, List<Person> people) {
    if (conversation.speakerResolution?.status != 'unavailable') return false;
    return conversation.transcriptSegments.any((segment) {
      if (segment.isUser || segment.speakerId == omiSpeakerId) return false;
      final person = personById(people, segment.personId);
      return person == null || person.name.trim().isEmpty;
    });
  }

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final people = context.watch<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople;
    final count = _speakerCount(conversation);
    final label = [l10n.transcript, if (count != null) l10n.transcriptSpeakerCount(count)].join(' · ');
    return Padding(
      padding: const EdgeInsets.only(top: 18, bottom: 18),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: ConversationDetailChip(
              key: const Key('conversation_transcript_heading'),
              icon: const Icon(Icons.notes),
              label: label,
            ),
          ),
          if (_hasUnnamedVoice(conversation, people))
            InkWell(
              key: const Key('transcript_unresolved_speakers_notice'),
              onTap: () => showOmiSheet<void>(
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
              ),
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
