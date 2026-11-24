import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/speaker_labels.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/person.dart';
import 'package:omi/pages/conversation_capturing/capture_recovery_status.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_tabs.dart';
import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/pages/conversations/widgets/live_conversation_end_button.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/pages/episodes/episode_content.dart';
import 'package:omi/pages/episodes/finish_capture.dart';
import 'package:omi/pages/episodes/live_episode_clock.dart';
import 'package:omi/pages/episodes/previous_episode_link.dart';
import 'package:omi/pages/episodes/live_transcript_view.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/conversations_v3_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/sockets/listen_client_state.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/conversations/conversation_title.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/capture_sources.dart';

/// Switch the home IndexedStack to Home (the conversation list) *before* popping the live route so
/// the user lands there with no flash of the previous page.
void switchHomeToConversationsTab(BuildContext context) {
  context.read<HomeProvider>().setIndex(HomeProvider.homeTab);
}

enum LiveEpisodeTab { summary, transcript }

/// What the episodes-off (and v3) live page shell shows. A record, so the select compares values.
typedef _LegacyShell = ({
  bool paused,
  bool callActive,
  bool verified,
  CaptureDisplayState state,
  Duration? bufferingFor,
  String? source,
  bool hasCapture,
  bool canPause,
});

/// The one live page, opened from Home's live row, the record button, notifications and the
/// capture deep link.
///
/// With episodes on (the server's capability) it is the live episode: today's conversation page in a
/// live state, Summary (running notes and captured tasks) and the
/// live Transcript, with "Wrap up now" at the bottom and Pause in the ⋯ menu. With episodes off it
/// is today's live capture page, unchanged: the transcript with Pause and Finish.
class LiveEpisodePage extends StatefulWidget {
  const LiveEpisodePage({
    super.key,
    this.topConversationId,
    this.rejectSpeaker,
    this.initialTab = LiveEpisodeTab.summary,
  });

  final String? topConversationId;
  final SpeakerRejectionCall? rejectSpeaker;
  final LiveEpisodeTab initialTab;

  @override
  State<LiveEpisodePage> createState() => LiveEpisodePageState();
}

class LiveEpisodePageState extends State<LiveEpisodePage> with SingleTickerProviderStateMixin {
  late final TabController _tabs;
  EpisodeProvider? _episodes;
  bool _mutePending = false;
  bool _finishing = false;

  /// The transcript on screen at the last Finish, kept until the server answers (and after a
  /// failure, with [_retryPending] so the next Finish sends it again).
  HeldCapture? _held;
  bool _retryPending = false;
  Timer? _tick;

  /// v3: Home stops re-reading the conversation in progress while this page covers it, so the page
  /// re-reads it itself; its title lands here when the server names it.
  Timer? _v3Refresh;

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this, initialIndex: widget.initialTab == LiveEpisodeTab.transcript ? 1 : 0);
    ListenClientState.instance.capturePageOpened();
    _episodes = context.read<EpisodeProvider?>();
    _episodes?.watch();
    // The running length and "updated N min ago" move on their own.
    _tick = Timer.periodic(const Duration(seconds: 30), (_) {
      if (mounted) setState(() {});
    });
    // Armed for every account: the v3 switch may answer after the page opens. Each tick reads only
    // for a v3 account, with the app in the foreground and this page on top, as Home's own read does.
    final v3 = context.read<ConversationsV3Provider?>();
    if (v3 != null) {
      _v3Refresh = Timer.periodic(const Duration(seconds: 15), (_) {
        if (!mounted || !v3.v3 || ModalRoute.of(context)?.isCurrent == false) return;
        final lifecycle = WidgetsBinding.instance.lifecycleState;
        if (lifecycle != null && lifecycle != AppLifecycleState.resumed) return;
        unawaited(v3.refresh());
      });
    }
  }

  @override
  void dispose() {
    _tick?.cancel();
    _v3Refresh?.cancel();
    _episodes?.unwatch();
    _tabs.dispose();
    ListenClientState.instance.capturePageClosed();
    super.dispose();
  }

  Future<void> _toggleMute(CaptureProvider provider) async {
    if (_mutePending) return;
    setState(() => _mutePending = true);
    try {
      OmiHaptics.medium();
      final phone = provider.liveCaptureSource == 'phone';
      if (provider.isPaused) {
        await provider.resumeCapture();
        if (phone && !provider.isPaused) PlatformManager.instance.analytics.phoneMicRecordingStarted();
      } else {
        await provider.pauseCapture();
        if (phone) PlatformManager.instance.analytics.phoneMicRecordingStopped();
      }
    } catch (_) {
      if (mounted) OmiFeedback.error(context, context.l10n.somethingWentWrong);
    } finally {
      if (mounted) setState(() => _mutePending = false);
    }
  }

  @visibleForTesting
  Future<void> debugStopConversation(CaptureProvider provider) => _stopConversation(provider);

  /// Finish (and Wrap Up Now): the one stop. No confirmation: it is explicit. It processes the
  /// conversation (a phone recording stops first) and opens it: its page when the server already
  /// made it, otherwise a processing page that turns into it ([finishLiveCapture],
  /// [presentFinishOutcome]). Until the server answers, and after a failure, the transcript the
  /// reader saw stays on screen; a failure keeps them here with Try Again, which sends it again.
  Future<void> _stopConversation(CaptureProvider provider) async {
    // One Finish at a time: a second tap while the first is processing would pop Home before the
    // conversation's page opens.
    if (_finishing || !mounted) return;
    final now = holdCapture(provider);
    final before = _held;
    setState(() {
      _finishing = true;
      _held = before == null
          ? now
          : now == null
              ? before
              : (segments: [...before.segments, ...now.segments], photos: [...before.photos, ...now.photos]);
    });
    var stays = false;
    try {
      final live = context.read<ConversationsV3Provider?>()?.live;
      final outcome = await finishLiveCapture(
        context,
        provider,
        episodes: _episodes,
        retry: _retryPending,
        owned: live != null && LiveConversationEndButton.phoneCaptures(live, provider, currentLiveId: live.id),
      );
      if (!mounted) return;
      stays = presentFinishOutcome(
        context,
        outcome,
        entry: FinishEntry.livePage,
        onRetry: () => _stopConversation(provider),
      );
      _retryPending = stays;
    } finally {
      if (mounted) {
        setState(() {
          _finishing = false;
          if (!stays) _held = null;
        });
      }
    }
  }

  // Home can open this page while the phone recorder is active but is still establishing
  // coordinator ownership, before either the capture source or its transcript is available.
  static bool _hasCapture(CaptureProvider capture) =>
      capture.liveCaptureSource != null ||
      EpisodePresentation.streamingSource(capture) != null ||
      capture.segments.isNotEmpty ||
      capture.photos.isNotEmpty;

  @override
  Widget build(BuildContext context) {
    final episodes = context.watch<EpisodeProvider?>();
    if (episodes == null || !episodes.enabled) {
      // v3 accounts always land here: their EpisodeProvider is suppressed. The shell (app bar,
      // Pause and Finish) selects only what it shows; the transcript subscribes itself. A
      // whole-page Consumer rebuilt the Scaffold on every capture notify (ingress health,
      // metrics, socket state) while a pendant streamed.
      return Builder(
        builder: (context) => _legacyPage(
          context,
          context.select<CaptureProvider, _LegacyShell>(
            (c) => (
              paused: c.isPaused,
              callActive: c.isCallActive,
              verified: c.pendantCaptureVerified,
              state: EpisodePresentation.displayState(c),
              bufferingFor: c.customSttBufferingDuration,
              source: c.liveCaptureSource,
              hasCapture: _hasCapture(c),
              canPause: EpisodePresentation.canPause(c),
            ),
          ),
        ),
      );
    }
    // The shell rebuilds only when its own state changes (anything capturing, the listening
    // state, pausability). Segment, photo, metric and progress notifies land in the selects
    // below: the transcript subscribes itself, and the summary and header select the
    // transcript version. A capture notifies several times a minute while live.
    final (listening, hasCapture, canPause) = context.select<CaptureProvider, (bool, bool, bool)>(
      (c) => (
        EpisodePresentation.isListening(EpisodePresentation.displayState(c)),
        _hasCapture(c),
        EpisodePresentation.canPause(c),
      ),
    );
    return _episodePage(context, episodes, listening, hasCapture, canPause);
  }

  // --------------------------------------------------------------------------- episodes off

  Widget _legacyPage(BuildContext context, _LegacyShell shell) {
    final effectivelyMuted = shell.paused || shell.callActive;
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: CaptureWedgeAppBar(
        showStatus: effectivelyMuted || shell.verified,
        state: shell.state,
        bufferingFor: shell.bufferingFor,
        sourceLabel: switch (shell.source) {
          null => null,
          'phone' => context.l10n.captureSourcePhoneMic,
          final source => CaptureSources.label(context, source),
        },
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const _V3LiveTitle(),
          Expanded(
            child: LiveTranscriptView(
              topConversationId: widget.topConversationId,
              rejectSpeaker: widget.rejectSpeaker,
              held: _held,
            ),
          ),
        ],
      ),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
      // Pause/Resume (a pause glyph: mics belong to Ask Omi) and Finish, the one stop.
      floatingActionButton: (shell.hasCapture || _finishing || _held != null)
          ? Row(
              mainAxisSize: MainAxisSize.min,
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                if (shell.canPause) ...[
                  OmiIconButton.filled(
                    key: const Key('capture_pause_button'),
                    icon: Icon(effectivelyMuted ? Icons.play_arrow_rounded : Icons.pause_rounded, size: 26),
                    label: effectivelyMuted ? context.l10n.resume : context.l10n.pause,
                    diameter: 52,
                    fillColor: OmiColors.surface3,
                    onPressed:
                        _mutePending || shell.callActive ? null : () => _toggleMute(context.read<CaptureProvider>()),
                  ),
                  const SizedBox(width: OmiSpacing.sm),
                ],
                OmiButton(
                  key: const Key('process_now_button'),
                  label: context.l10n.finish,
                  leading: const Icon(Icons.check_rounded),
                  isLoading: _finishing,
                  onPressed: () => _stopConversation(context.read<CaptureProvider>()),
                ),
              ],
            )
          : null,
    );
  }

  // --------------------------------------------------------------------------- episodes on

  Widget _episodePage(BuildContext context, EpisodeProvider episodes, bool listening, bool hasCapture, bool canPause) {
    final l10n = context.l10n;
    final episode = episodes.live;
    final now = episodes.now();
    return Scaffold(
      key: const Key('live_episode_page'),
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        automaticallyImplyLeading: false,
        // Pinned and opaque in the page's own colour: the tabs' content scrolls beneath the
        // header, never visibly under it, and no scrolled-under tint sets the bar apart.
        backgroundColor: OmiColors.surface0,
        surfaceTintColor: Colors.transparent,
        scrolledUnderElevation: 0,
        leading: const Center(child: OmiBackButton.circled()),
        titleSpacing: 0,
        actions: [
          if (canPause)
            Padding(
              padding: const EdgeInsetsDirectional.only(end: OmiSpacing.xs),
              child: OmiIconButton.filled(
                key: const Key('live_episode_more'),
                icon: const Icon(Icons.more_horiz_rounded, size: 20),
                label: l10n.moreOptions,
                onPressed: () => _openMenu(context, context.read<CaptureProvider>()),
              ),
            ),
        ],
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          ColoredBox(
            key: const Key('live_episode_pinned_header'),
            color: OmiColors.surface0,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // Pinned above the tabs, so it scales only so far: at the largest sizes the
                // title would otherwise leave the tab content a sliver of the screen.
                MediaQuery.withClampedTextScaling(
                  maxScaleFactor: 2,
                  child: _header(context, episode, now, listening: listening),
                ),
                ConversationDetailTabs(controller: _tabs, onTap: (_) {}, showVisibility: false),
              ],
            ),
          ),
          Expanded(
            child: TabBarView(
              controller: _tabs,
              children: [
                // The running notes follow the episode (the 30-second poll and wrap-up), not
                // the transcript: lines arrive several times a minute, moments do not.
                _LiveSummaryTab(
                  episode: episode,
                  now: now,
                  unavailable: episodes.notesUnavailable(
                    captureStart: context.select<CaptureProvider, DateTime?>((c) => c.liveCaptureStartedAt),
                    captureId: context.select<CaptureProvider, String?>(
                      (c) => c.liveCaptureSource == 'phone' ? c.activeRecordingId : null,
                    ),
                  ),
                  // The admitted preview session, when this capture has one: its on-device notes
                  // (So far) hang off it.
                  preview: context.select<CaptureProvider, LivePreviewController?>(
                    (c) => c.localPreviewAdmitted && c.livePreview?.admitted == true ? c.livePreview : null,
                  ),
                  onDismiss: (item) => _dismiss(context, episodes, item),
                ),
                LiveTranscriptView(
                  topConversationId: widget.topConversationId,
                  rejectSpeaker: widget.rejectSpeaker,
                  episode: episode ?? _emptyEpisode(now),
                  onDismissItem: (item) => _dismiss(context, episodes, item),
                  jumpToLatestBottom: 120,
                  held: _held,
                ),
              ],
            ),
          ),
        ],
      ),
      bottomNavigationBar: hasCapture || _finishing || _held != null
          ? _wrapUpBar(context, episodes, paused: context.select<CaptureProvider, bool>((c) => c.isPaused))
          : null,
    );
  }

  /// A placeholder so the transcript draws the episode layout before the first moment lands.
  static Episode _emptyEpisode(DateTime now) => Episode(id: '', live: true, startedAt: now, lastActivityAt: now);

  Future<void> _dismiss(BuildContext context, EpisodeProvider episodes, EpisodeItem item) async {
    final ok = await episodes.dismissItem(item.id);
    if (!ok && context.mounted) OmiFeedback.error(context, context.l10n.somethingWentWrongTryAgain);
  }

  void _openMenu(BuildContext context, CaptureProvider provider) {
    final paused = provider.isPaused || provider.isCallActive;
    showOmiRowMenu(
      context,
      actions: [
        OmiMenuAction(
          icon: paused ? Icons.play_arrow_rounded : Icons.pause_rounded,
          label: paused ? context.l10n.resumeRecording : context.l10n.pauseRecording,
          onSelected: () => _toggleMute(provider),
        ),
      ],
    );
  }

  Widget _header(BuildContext context, Episode? episode, DateTime now, {required bool listening}) {
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    // The header walks every line to name the participants; rebuild only when the
    // transcript (or the people list) actually changes, not on every capture notify.
    return Builder(
      builder: (context) {
        context.select<CaptureProvider, int>((c) => c.segmentsPhotosVersion);
        final provider = context.read<CaptureProvider>();
        final people = context.watch<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople;
        final anchor = context.read<EpisodeProvider?>()?.liveAnchor;
        final started =
            episode?.startedAt ?? now.subtract(EpisodePresentation.elapsed(null, provider, now, anchor: anchor));
        // Named from the transcript's own speaker resolution, so the header and the lines agree.
        final participants = _participantsMemo(provider, people);
        final title = (episode?.title ?? '').trim().isEmpty ? l10n.episodeListeningNow : episode!.title;
        final namesOthers = participants.length > (provider.segments.any((s) => s.isUser) ? 1 : 0);
        final meta = OmiType.subhead.copyWith(color: OmiColors.textSecondary);
        final names = namesOthers ? participants.join(', ') : '';
        final rest = listening ? l10n.episodeLiveSince(dates.time(started)) : (names.isEmpty ? '' : '· $names');
        return Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xxs, OmiSpacing.md, OmiSpacing.sm),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(title, style: OmiType.title1.copyWith(height: 1.15, letterSpacing: -0.4)),
              const SizedBox(height: OmiSpacing.xs),
              // One calm line, "Listening · 1h 36m · since 9:21 AM", ellipsized rather than wrapped.
              CaptureStateAnnouncement(
                message: listening
                    ? l10n.episodeListeningNow
                    : captureStateLabel(l10n, EpisodePresentation.displayState(provider)),
                child: Row(
                  children: [
                    Flexible(
                      child: LiveEpisodeClock(
                        clock: context.read<EpisodeProvider>().now,
                        builder: (context, time) {
                          final length = EpisodePresentation.runningLength(
                            EpisodePresentation.elapsed(episode, provider, time, anchor: anchor),
                            l10n,
                          );
                          return Text(
                            listening
                                ? '${l10n.listening} · $length'
                                : captureStateLabel(l10n, EpisodePresentation.displayState(provider)),
                            key: const Key('live_episode_status'),
                            semanticsLabel: listening
                                ? (episode == null ? l10n.episodeCaptureFor : l10n.episodeLiveFor)(length)
                                : null,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: meta.copyWith(fontFeatures: const [FontFeature.tabularFigures()]),
                          );
                        },
                      ),
                    ),
                    if (rest.isNotEmpty) ...[
                      const SizedBox(width: 4),
                      Flexible(
                        child: Text(
                          rest,
                          key: const Key('live_episode_meta'),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: meta,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
              const PreviousEpisodeLink(),
            ],
          ),
        );
      },
    );
  }

  // The participant names walk every line, so they are rebuilt only when the transcript
  // version or the people list changes.
  int _participantsKey = -1;
  List<String>? _participantsCache;

  List<String> _participantsMemo(CaptureProvider capture, List<Person> people) {
    final key = Object.hash(capture.segmentsPhotosVersion, identityHashCode(people));
    if (_participantsKey != key || _participantsCache == null) {
      _participantsKey = key;
      _participantsCache = EpisodePresentation.participants(capture.segments, people, context.l10n);
    }
    return _participantsCache!;
  }

  Future<void> _resume(CaptureProvider provider) async {
    try {
      await provider.resumeCapture();
    } catch (_) {
      if (mounted) OmiFeedback.error(context, context.l10n.somethingWentWrong);
    }
  }

  /// Wrap up, or while paused one tap to resume first, with Wrap up beneath it.
  Widget _wrapUpBar(BuildContext context, EpisodeProvider episodes, {required bool paused}) {
    final l10n = context.l10n;
    return DecoratedBox(
      decoration: BoxDecoration(
        color: OmiColors.surface0,
        border: Border(top: BorderSide(color: OmiColors.surface1)),
      ),
      child: SafeArea(
        top: false,
        child: Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, OmiSpacing.sm),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text(
                l10n.episodeWrapsUpHint,
                textAlign: TextAlign.center,
                style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
              ),
              const SizedBox(height: OmiSpacing.xs),
              if (paused) ...[
                OmiButton(
                  key: const Key('episode_resume_button'),
                  label: l10n.resume,
                  expand: true,
                  onPressed: () => _resume(context.read<CaptureProvider>()),
                ),
                const SizedBox(height: OmiSpacing.xs),
              ],
              OmiButton(
                key: const Key('episode_wrap_up_button'),
                label: l10n.episodeWrapUpNow,
                expand: true,
                variant: paused ? OmiButtonVariant.secondary : OmiButtonVariant.primary,
                isLoading: episodes.wrappingUp || _finishing,
                onPressed: () => _stopConversation(context.read<CaptureProvider>()),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Summary of a live episode: the running notes and the tasks captured so far. The newest words
/// are on the Transcript tab.
class _LiveSummaryTab extends StatelessWidget {
  const _LiveSummaryTab({
    required this.episode,
    required this.now,
    required this.unavailable,
    required this.preview,
    required this.onDismiss,
  });

  final Episode? episode;
  final DateTime now;
  final bool unavailable;
  final LivePreviewController? preview;
  final ValueChanged<EpisodeItem> onDismiss;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final items = episode?.visibleItems ?? const <EpisodeItem>[];
    return ListView(
      key: const Key('live_episode_summary'),
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.md, OmiSpacing.md, OmiSpacing.xl),
      children: [
        _SoFarCard(episode: episode, now: now, unavailable: unavailable, preview: preview),
        if (items.isNotEmpty) ...[
          EpisodeSectionTitle(l10n.tasks, count: items.length),
          EpisodeContentCard(
            children: [for (final item in items) EpisodeItemRow(item: item, now: now, onDismiss: onDismiss)],
          ),
        ],
      ],
    );
  }
}

class _SoFarCard extends StatelessWidget {
  const _SoFarCard({required this.episode, required this.now, required this.unavailable, required this.preview});

  final Episode? episode;
  final DateTime now;
  final bool unavailable;

  /// The admitted local-preview session, or null when this capture streams to the cloud.
  final LivePreviewController? preview;

  /// The card stays a glance while the episode runs; the full notes arrive when it wraps up.
  static const maxBullets = 4;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final bullets = episode?.bullets ?? const <String>[];
    final serverNotes = episode != null && bullets.isNotEmpty;
    // A preview session has no server running notes by design — the batch record
    // arrives at the end — so "aren't updating" would name a failure of something
    // that was never supposed to run.
    final notesUnavailable = unavailable && preview == null;
    return Container(
      key: const Key('live_episode_so_far'),
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(l10n.episodeSoFar, style: OmiType.headline),
          if (notesUnavailable) ...[
            const SizedBox(height: OmiSpacing.xs),
            Text(
              l10n.episodeNotesUnavailable,
              key: const Key('episode_notes_unavailable'),
              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
            ),
          ],
          if (serverNotes) ...[
            const SizedBox(height: 2),
            Text(
              EpisodePresentation.coversLabel(episode!, now, l10n, OmiDateFormat.of(context)),
              key: const Key('live_episode_so_far_covers'),
              style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
            ),
            const SizedBox(height: OmiSpacing.sm),
            // The newest notes: a long episode's earlier ones return with the full notes.
            EpisodeBullets(bullets.length > maxBullets ? bullets.sublist(bullets.length - maxBullets) : bullets),
          ] else if (preview != null) ...[
            // Notes drafted on this phone from the preview text; the quiet line while
            // there is nothing to draft (no engine, Apple Intelligence off, or the
            // first words not summarized yet). There is no cloud fallback.
            ListenableBuilder(
              listenable: preview!.notes,
              builder: (context, _) {
                final notes = preview!.notes;
                if (notes.bullets.isEmpty) {
                  return Padding(
                    key: const Key('episode_notes_start_with_transcript'),
                    padding: const EdgeInsets.only(top: OmiSpacing.xs),
                    child: Text(
                      l10n.episodeNotesStartWithTranscript,
                      style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                    ),
                  );
                }
                return Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  key: const Key('episode_on_device_notes'),
                  children: [
                    const SizedBox(height: OmiSpacing.sm),
                    EpisodeBullets(notes.bullets.take(maxBullets).toList()),
                  ],
                );
              },
            ),
          ] else if (!unavailable) ...[
            const SizedBox(height: OmiSpacing.xs),
            Text(l10n.episodeNotesSoon, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          ],
        ],
      ),
    );
  }
}

/// v3: the conversation in progress's title over its transcript, "Listening" (Home's live row title)
/// until the server names it. Nothing for an account off v3.
class _V3LiveTitle extends StatelessWidget {
  const _V3LiveTitle();

  @override
  Widget build(BuildContext context) {
    final (v3, title) = context.select<ConversationsV3Provider?, (bool, String)>((p) {
      final live = p?.live;
      return (p?.v3 ?? false, live == null ? '' : presentableConversationTitle(live));
    });
    if (!v3) return const SizedBox.shrink();
    return Padding(
      key: const Key('live_page_v3_title'),
      padding: const EdgeInsetsDirectional.fromSTEB(16, 4, 16, 8),
      child: Text(
        title.isEmpty ? context.l10n.listening : title,
        style: OmiType.title1.copyWith(height: 1.15, letterSpacing: -0.4),
        maxLines: 2,
        overflow: TextOverflow.ellipsis,
      ),
    );
  }
}
