import 'dart:async';

import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/speaker_labels.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/backend/schema/conversation.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/pages/conversation_capturing/capture_recovery_status.dart';
import 'package:omi/pages/conversation_detail/widgets/conversation_detail_tabs.dart';
import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/pages/episodes/live_episode_clock.dart';
import 'package:omi/pages/episodes/live_transcript_view.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/home_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/services/sockets/listen_client_state.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/capture_sources.dart';
import 'package:omi/widgets/speaker_label.dart';

/// Switch the home IndexedStack to Home (the conversation list) *before* popping the live route so
/// the user lands there with no flash of the previous page.
void switchHomeToConversationsTab(BuildContext context) {
  context.read<HomeProvider>().setIndex(HomeProvider.homeTab);
}

enum LiveEpisodeTab { summary, transcript }

/// The one live page, opened from Home's live row, the record button, notifications and the
/// capture deep link.
///
/// With episodes on (the server's capability) it is the live episode: today's conversation page in a
/// live state, Summary (running notes, captured tasks, a transcript preview, the moments) and the
/// live Transcript, with "Wrap Up Now" at the bottom and Pause in the ⋯ menu. With episodes off it
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
  Timer? _tick;

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
  }

  @override
  void dispose() {
    _tick?.cancel();
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

  /// Finish (and Wrap Up Now): the one stop. No confirmation: it is explicit, and it processes the
  /// conversation (a phone recording stops first; a pendant it paused resumes afterwards). With an
  /// episode, the server closes it once that conversation's notes are done.
  Future<void> _stopConversation(CaptureProvider provider) async {
    final hadContent = provider.segments.isNotEmpty || provider.photos.isNotEmpty;
    final episodes = _episodes;
    if (episodes != null && episodes.enabled && episodes.live != null) {
      final conversationId = hadContent ? (widget.topConversationId ?? provider.topConversationId) : null;
      unawaited(episodes.wrapUp(conversationId: conversationId));
    }
    if (hadContent) {
      await provider.finishCapture();
      if (!mounted) return;
      switchHomeToConversationsTab(context);
    } else {
      final source = provider.liveCaptureSource;
      if (source == null || source == ConversationSource.phone.name) {
        await provider.stopStreamRecording();
      } else if (EpisodePresentation.canPause(provider) && !provider.isPaused) {
        await provider.pauseCapture();
      }
    }
    if (!mounted) return;
    // A swipe back during the finish has already popped this route; it only stays mounted while it
    // animates out, and a pop then would take Home with it and leave the navigator empty.
    final route = ModalRoute.of(context);
    if (route != null && route.isCurrent) Navigator.of(context).pop();
  }

  @override
  Widget build(BuildContext context) {
    final episodes = context.watch<EpisodeProvider?>();
    return Consumer<CaptureProvider>(
      builder: (context, provider, child) {
        if (episodes == null || !episodes.enabled) return _legacyPage(context, provider);
        return _episodePage(context, provider, episodes);
      },
    );
  }

  // --------------------------------------------------------------------------- episodes off

  Widget _legacyPage(BuildContext context, CaptureProvider provider) {
    final effectivelyMuted = provider.isPaused || provider.isCallActive;
    return Scaffold(
      backgroundColor: OmiColors.surface0,
      appBar: CaptureWedgeAppBar(
        showStatus: effectivelyMuted || provider.pendantCaptureVerified,
        state: EpisodePresentation.displayState(provider),
        bufferingFor: provider.customSttBufferingDuration,
        sourceLabel: switch (provider.liveCaptureSource) {
          null => null,
          'phone' => context.l10n.captureSourcePhoneMic,
          final source => CaptureSources.label(context, source),
        },
      ),
      body: LiveTranscriptView(topConversationId: widget.topConversationId, rejectSpeaker: widget.rejectSpeaker),
      floatingActionButtonLocation: FloatingActionButtonLocation.centerFloat,
      // Pause/Resume (a pause glyph: mics belong to Ask Omi) and Finish, the one stop.
      floatingActionButton:
          (provider.liveCaptureSource != null || provider.segments.isNotEmpty || provider.photos.isNotEmpty)
              ? Row(
                  mainAxisSize: MainAxisSize.min,
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    if (EpisodePresentation.canPause(provider)) ...[
                      OmiIconButton.filled(
                        key: const Key('capture_pause_button'),
                        icon: Icon(effectivelyMuted ? Icons.play_arrow_rounded : Icons.pause_rounded, size: 26),
                        label: effectivelyMuted ? context.l10n.resume : context.l10n.pause,
                        diameter: 52,
                        fillColor: OmiColors.surface3,
                        onPressed: _mutePending || provider.isCallActive ? null : () => _toggleMute(provider),
                      ),
                      const SizedBox(width: OmiSpacing.sm),
                    ],
                    OmiButton(
                      key: const Key('process_now_button'),
                      label: context.l10n.finish,
                      leading: const Icon(Icons.check_rounded),
                      onPressed: () => _stopConversation(provider),
                    ),
                  ],
                )
              : null,
    );
  }

  // --------------------------------------------------------------------------- episodes on

  Widget _episodePage(BuildContext context, CaptureProvider provider, EpisodeProvider episodes) {
    final l10n = context.l10n;
    final episode = episodes.live;
    final now = episodes.now();
    final state = EpisodePresentation.displayState(provider);
    final listening = EpisodePresentation.isListening(state);
    final conversationId = widget.topConversationId ?? provider.topConversationId;
    final hasCapture = provider.liveCaptureSource != null || provider.segments.isNotEmpty || provider.photos.isNotEmpty;
    return Scaffold(
      key: const Key('live_episode_page'),
      backgroundColor: OmiColors.surface0,
      appBar: AppBar(
        automaticallyImplyLeading: false,
        leading: const Center(child: OmiBackButton.circled()),
        titleSpacing: 0,
        actions: [
          if (EpisodePresentation.canPause(provider))
            Padding(
              padding: const EdgeInsetsDirectional.only(end: OmiSpacing.xs),
              child: OmiIconButton.filled(
                key: const Key('live_episode_more'),
                icon: const Icon(Icons.more_horiz_rounded, size: 20),
                label: l10n.moreOptions,
                onPressed: () => _openMenu(context, provider),
              ),
            ),
        ],
      ),
      body: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          _header(context, provider, episode, now, state: state, listening: listening),
          ConversationDetailTabs(controller: _tabs, onTap: (_) {}, showVisibility: false),
          Expanded(
            child: TabBarView(
              controller: _tabs,
              children: [
                _LiveSummaryTab(
                  episode: episode,
                  now: now,
                  conversationId: conversationId,
                  segments: provider.segments,
                  listening: listening && hasCapture,
                  onOpenTranscript: () => _tabs.animateTo(1),
                  onDismiss: (item) => _dismiss(context, episodes, item),
                ),
                LiveTranscriptView(
                  topConversationId: widget.topConversationId,
                  rejectSpeaker: widget.rejectSpeaker,
                  episode: episode ?? _emptyEpisode(now),
                  onDismissItem: (item) => _dismiss(context, episodes, item),
                  jumpToLatestBottom: 120,
                ),
              ],
            ),
          ),
        ],
      ),
      bottomNavigationBar: hasCapture ? _wrapUpBar(context, provider, episodes) : null,
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

  Widget _header(
    BuildContext context,
    CaptureProvider provider,
    Episode? episode,
    DateTime now, {
    required CaptureDisplayState state,
    required bool listening,
  }) {
    final l10n = context.l10n;
    final dates = OmiDateFormat.of(context);
    final started = episode?.startedAt ?? now.subtract(EpisodePresentation.elapsed(null, provider, now));
    final title = (episode?.title ?? '').trim().isEmpty ? l10n.episodeListeningNow : episode!.title;
    // Named from the transcript's own speaker resolution, so the header and the lines agree.
    final people = EpisodePresentation.participants(
      provider.segments,
      context.watch<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople,
      l10n,
    );
    final namesOthers = people.length > (provider.segments.any((s) => s.isUser) ? 1 : 0);
    final moments = episode?.moments.length ?? 0;
    final meta = OmiType.subhead.copyWith(color: OmiColors.textSecondary);
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xxs, OmiSpacing.md, OmiSpacing.sm),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: OmiType.title1.copyWith(height: 1.15, letterSpacing: -0.4)),
          const SizedBox(height: OmiSpacing.xs),
          Wrap(
            spacing: OmiSpacing.sm,
            runSpacing: OmiSpacing.xxs,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Semantics(
                liveRegion: true,
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    OmiLiveDot(live: listening, size: 7),
                    const SizedBox(width: 6),
                    LiveEpisodeClock(
                      clock: context.read<EpisodeProvider>().now,
                      builder: (context, time) => Text(
                        listening
                            ? l10n.episodeLiveFor(EpisodePresentation.runningLength(
                                EpisodePresentation.elapsed(episode, provider, time), l10n))
                            : captureStateLabel(l10n, state),
                        key: const Key('live_episode_status'),
                        style: meta.copyWith(
                          color: listening ? OmiColors.success : OmiColors.textSecondary,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Text('${dates.dayHeader(started)} · ${dates.time(started)}', style: meta),
              if (namesOthers) Text(people.join(', '), style: meta),
              if (moments > 1) Text(l10n.episodeMomentsCount(moments), style: meta),
            ],
          ),
        ],
      ),
    );
  }

  Widget _wrapUpBar(BuildContext context, CaptureProvider provider, EpisodeProvider episodes) {
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
              OmiButton(
                key: const Key('episode_wrap_up_button'),
                label: l10n.episodeWrapUpNow,
                expand: true,
                isLoading: episodes.wrappingUp,
                onPressed: () => _stopConversation(provider),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

/// Summary of a live episode: the running notes, the tasks captured so far, a preview of the
/// transcript and the moments, the current one marked Now.
class _LiveSummaryTab extends StatelessWidget {
  const _LiveSummaryTab({
    required this.episode,
    required this.now,
    required this.conversationId,
    required this.segments,
    required this.listening,
    required this.onOpenTranscript,
    required this.onDismiss,
  });

  final Episode? episode;
  final DateTime now;
  final String? conversationId;
  final List<TranscriptSegment> segments;
  final bool listening;
  final VoidCallback onOpenTranscript;
  final ValueChanged<EpisodeItem> onDismiss;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final items = episode?.visibleItems ?? const <EpisodeItem>[];
    final moments = episode?.moments ?? const <EpisodeMoment>[];
    return ListView(
      key: const Key('live_episode_summary'),
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.md, OmiSpacing.md, OmiSpacing.xl),
      children: [
        _SoFarCard(episode: episode, now: now),
        if (items.isNotEmpty) ...[
          _SectionTitle(l10n.tasks, count: items.length),
          _Card(
            children: [
              for (final item in items) _ItemRow(item: item, now: now, onDismiss: onDismiss),
            ],
          ),
        ],
        if (segments.isNotEmpty) ...[
          _SectionTitle(
            l10n.liveTranscript,
            trailing: OmiButton.tertiary(
              key: const Key('live_episode_open_transcript'),
              label: l10n.episodeOpenAll,
              size: OmiButtonSize.compact,
              onPressed: onOpenTranscript,
            ),
          ),
          _TranscriptPreview(segments: segments),
        ],
        if (moments.isNotEmpty) ...[
          _SectionTitle(l10n.episodeMoments),
          _Card(
            children: [
              for (var i = 0; i < moments.length; i++)
                _MomentRow(
                  moment: moments[i],
                  current: listening && i == moments.length - 1 && moments[i].conversationId == conversationId,
                ),
            ],
          ),
        ],
      ],
    );
  }
}

class _SectionTitle extends StatelessWidget {
  const _SectionTitle(this.title, {this.count, this.trailing});

  final String title;
  final int? count;
  final Widget? trailing;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.xxs, OmiSpacing.lg, 0, OmiSpacing.xs),
      child: Row(
        children: [
          Expanded(
            child: Text.rich(
              TextSpan(
                text: title,
                style: OmiType.headline,
                children: [
                  if (count != null)
                    TextSpan(
                      text: '  $count',
                      style: OmiType.headline.copyWith(color: OmiColors.textTertiary, fontWeight: FontWeight.w400),
                    ),
                ],
              ),
            ),
          ),
          if (trailing != null) trailing!,
        ],
      ),
    );
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.children});

  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    final rows = <Widget>[];
    for (var i = 0; i < children.length; i++) {
      if (i > 0) rows.add(Container(height: 1, color: OmiColors.surface2));
      rows.add(children[i]);
    }
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(crossAxisAlignment: CrossAxisAlignment.stretch, children: rows),
    );
  }
}

class _SoFarCard extends StatelessWidget {
  const _SoFarCard({required this.episode, required this.now});

  final Episode? episode;
  final DateTime now;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final bullets = episode?.bullets ?? const <String>[];
    return Container(
      key: const Key('live_episode_so_far'),
      padding: const EdgeInsets.all(OmiSpacing.md),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(l10n.episodeSoFar, style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600)),
          if (episode != null && bullets.isNotEmpty) ...[
            const SizedBox(height: 2),
            Text(
              EpisodePresentation.updatedLabel(episode!, now, l10n),
              style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
            ),
            const SizedBox(height: OmiSpacing.sm),
            for (final bullet in bullets)
              Padding(
                padding: const EdgeInsets.only(bottom: OmiSpacing.xs),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('•  ', style: OmiType.callout.copyWith(color: OmiColors.textTertiary, height: 1.4)),
                    Expanded(child: Text(bullet, style: OmiType.callout.copyWith(height: 1.4))),
                  ],
                ),
              ),
          ] else ...[
            const SizedBox(height: OmiSpacing.xs),
            Text(l10n.episodeNotesSoon, style: OmiType.subhead.copyWith(color: OmiColors.textSecondary)),
          ],
        ],
      ),
    );
  }
}

class _ItemRow extends StatelessWidget {
  const _ItemRow({required this.item, required this.now, required this.onDismiss});

  final EpisodeItem item;
  final DateTime now;
  final ValueChanged<EpisodeItem> onDismiss;

  @override
  Widget build(BuildContext context) {
    final saved = item.status == EpisodeItemStatus.kept;
    final fresh = now.difference(item.createdAt).inMinutes < 2;
    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 48),
      child: Row(
        children: [
          Icon(
            saved ? Icons.check_circle_rounded : (item.isReminder ? Icons.alarm_rounded : Icons.radio_button_unchecked),
            size: 22,
            color: saved ? OmiColors.textPrimary : OmiColors.textTertiary,
          ),
          const SizedBox(width: OmiSpacing.sm),
          Expanded(child: Text(item.text, style: OmiType.callout)),
          const SizedBox(width: OmiSpacing.xs),
          Text(
            fresh ? context.l10n.episodeNow : OmiDateFormat.of(context).time(item.createdAt),
            style: OmiType.footnote.copyWith(color: fresh ? OmiColors.success : OmiColors.textTertiary),
          ),
          if (!saved)
            OmiIconButton(
              key: ValueKey('episode_item_dismiss_${item.id}'),
              icon: Icon(Icons.close_rounded, size: 18, color: OmiColors.textTertiary),
              label: context.l10n.undo,
              onPressed: () => onDismiss(item),
            ),
        ],
      ),
    );
  }
}

class _TranscriptPreview extends StatelessWidget {
  const _TranscriptPreview({required this.segments});

  final List<TranscriptSegment> segments;

  @override
  Widget build(BuildContext context) {
    final people = context.watch<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople;
    final names = SpeakerNames.forSegments(segments, people: people, l10n: context.l10n);
    final tail = segments.length > 3 ? segments.sublist(segments.length - 3) : segments;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
      decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          for (var i = 0; i < tail.length; i++)
            Padding(
              padding: EdgeInsets.only(top: i == 0 ? 0 : OmiSpacing.xs),
              child: Text.rich(
                TextSpan(
                  children: [
                    TextSpan(
                      text: '${names.forSegment(tail[i], person: personById(people, tail[i].personId))}  ',
                      style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
                    ),
                    TextSpan(text: tail[i].text),
                  ],
                ),
                style: OmiType.subhead.copyWith(
                  height: 1.4,
                  // The newest line reads brightest; older lines step back.
                  color: i == tail.length - 1 ? OmiColors.textPrimary : OmiColors.textSecondary,
                ),
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
              ),
            ),
        ],
      ),
    );
  }
}

class _MomentRow extends StatelessWidget {
  const _MomentRow({required this.moment, required this.current});

  final EpisodeMoment moment;
  final bool current;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final when = current ? l10n.episodeNow : OmiDateFormat.of(context).time(moment.startedAt);
    final tint = current ? OmiColors.success : OmiColors.textTertiary;
    return ConstrainedBox(
      constraints: const BoxConstraints(minHeight: 46),
      child: Row(
        children: [
          SizedBox(width: 64, child: Text(when, style: OmiType.footnote.copyWith(color: tint))),
          Expanded(child: Text(moment.heading.isEmpty ? '—' : moment.heading, style: OmiType.callout)),
          Text(
            EpisodePresentation.runningLength(moment.duration, l10n),
            style: OmiType.footnote.copyWith(color: tint),
          ),
        ],
      ),
    );
  }
}
