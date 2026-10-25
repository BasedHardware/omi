import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/pages/episodes/live_episode_clock.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Home's live episode: the first row of Today. An outlined card, quieter than the filled rows
/// around it, with a small breathing dot, the episode's running topic, and "Live · 24m · 2 people".
/// It scrolls with the list; there is no overlay and nothing sticks to the header. Opens the live
/// episode.
class LiveEpisodeRow extends StatefulWidget {
  const LiveEpisodeRow({super.key});

  @override
  State<LiveEpisodeRow> createState() => _LiveEpisodeRowState();
}

class _LiveEpisodeRowState extends State<LiveEpisodeRow> {
  EpisodeProvider? _episodes;
  int? _peopleKey;
  int _people = 0;

  /// How many people the transcript names: the owner plus speakers resolved to the user's people,
  /// as the live page's header names them. Raw diarization ids are not people (a long session
  /// hands out hundreds), so unresolved voices never count. Recounted only when the transcript or
  /// the people list changes; the row itself rebuilds every second for its clock.
  int _peopleCount(CaptureProvider capture) {
    final people = context.read<PeopleProvider?>()?.people ?? SharedPreferencesUtil().cachedPeople;
    final key = Object.hash(capture.segmentsPhotosVersion, identityHashCode(people));
    if (_peopleKey != key) {
      _peopleKey = key;
      _people = EpisodePresentation.participants(capture.segments, people, context.l10n).length;
    }
    return _people;
  }

  @override
  void initState() {
    super.initState();
    _episodes = context.read<EpisodeProvider?>();
    _episodes?.watch();
  }

  @override
  void dispose() {
    _episodes?.unwatch();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final episodes = context.watch<EpisodeProvider>();
    // Only what the row draws: the capture state, its start and whether it streams. Transcript
    // lines, socket chatter and BLE samples no longer rebuild the row (the 1 s clock still ticks).
    final (state, _, _) = context.select<CaptureProvider, (CaptureDisplayState, DateTime?, String?)>(
      (c) => (EpisodePresentation.displayState(c), c.liveCaptureStartedAt, EpisodePresentation.streamingSource(c)),
    );
    return LiveEpisodeClock(
      clock: episodes.now,
      builder: (context, now) => _row(context, episodes, context.read<CaptureProvider>(), state, now),
    );
  }

  Widget _row(
    BuildContext context,
    EpisodeProvider episodes,
    CaptureProvider capture,
    CaptureDisplayState state,
    DateTime now,
  ) {
    final l10n = context.l10n;
    final episode = episodes.live;
    final listening = EpisodePresentation.isListening(state);
    final running = EpisodePresentation.elapsed(episode, capture, now, anchor: episodes.liveAnchor);
    // Seconds only while the first minute runs; after that whole minutes, as the rows below read.
    final elapsed = running.inSeconds < 60
        ? EpisodePresentation.runningLength(running, l10n)
        : OmiDuration.compact(running.inMinutes * 60, l10n);
    final named = (episode?.title ?? '').trim();
    final title = named.isEmpty ? l10n.episodeListeningNow : named;
    final topics = named.isEmpty ? EpisodePresentation.topics(episode) : '';
    final peopleNamed = _peopleCount(capture);
    // Paused (or waiting) shows no clock: a time that keeps counting while nothing listens misleads.
    final status = listening
        ? (episode == null ? l10n.episodeCaptureFor : l10n.episodeLiveFor)(elapsed)
        : captureStateLabel(l10n, state);
    final rest = [
      status,
      if (peopleNamed >= 2) l10n.peopleCount(peopleNamed),
      if (topics.isNotEmpty) topics,
    ].join(' · ');
    void open() {
      OmiHaptics.selection();
      PlatformManager.instance.analytics.liveTranscriptCardClicked(
        hasSegments: capture.segments.isNotEmpty,
        hasPhotos: capture.photos.isNotEmpty,
        segmentCount: capture.segments.length,
        photoCount: capture.photos.length,
      );
      routeToPage(context, LiveEpisodePage(topConversationId: capture.topConversationId));
    }

    return Padding(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16),
      child: CaptureStateAnnouncement(
        message: listening ? l10n.episodeListeningNow : captureStateLabel(l10n, state),
        child: Semantics(
          button: true,
          label: '$title, $rest',
          onTap: open,
          excludeSemantics: true,
          child: Material(
            key: const Key('home_live_episode_row'),
            // Outlined, not filled: the one row still happening reads as distinct from finished
            // ones without a colored tile.
            color: Colors.transparent,
            shape: RoundedRectangleBorder(borderRadius: OmiRadius.xlAll, side: BorderSide(color: OmiColors.border)),
            clipBehavior: Clip.antiAlias,
            child: InkWell(
              onTap: open,
              child: Padding(
                padding: const EdgeInsetsDirectional.fromSTEB(14, 14, 10, 14),
                child: Row(
                  children: [
                    Container(
                      width: 36,
                      height: 36,
                      alignment: Alignment.center,
                      decoration: BoxDecoration(
                        borderRadius: OmiRadius.mdAll,
                        border: Border.all(color: OmiColors.border),
                      ),
                      child: OmiBreathingDot(live: listening),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            title,
                            style: Theme.of(context).textTheme.titleMedium,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          const SizedBox(height: 3),
                          Text(
                            rest,
                            style: OmiType.subhead.copyWith(color: OmiColors.textTertiary),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ],
                      ),
                    ),
                    Icon(Icons.chevron_right_rounded, color: OmiColors.textDisabled),
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
