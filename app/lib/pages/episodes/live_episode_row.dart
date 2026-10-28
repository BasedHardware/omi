import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/pages/episodes/live_episode_clock.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/pages/episodes/start_trimmed_text.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/providers/people_provider.dart';
import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_coverage.dart';
import 'package:omi/backend/preferences.dart';
import 'package:omi/l10n/app_localizations.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/alerts/app_snackbar.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Home's live episode: the first row of Today. An outlined card, quieter than the filled rows
/// around it: a tile with the running length ("24m"), the episode's title,
/// and on line two the newest preview words (trimmed at the start) or "2 people · topic".
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
    // Only what the row draws: the capture state, its start, whether it streams, and whether
    // the reader's Reconnect is still running (the button waits on it). Transcript lines,
    // socket chatter and BLE samples no longer rebuild the row (the 1 s clock still ticks).
    final (state, _, _, reconnecting) =
        context.select<CaptureProvider, (CaptureDisplayState, DateTime?, String?, bool)>(
      (c) => (
        EpisodePresentation.displayState(c),
        c.liveCaptureStartedAt,
        EpisodePresentation.streamingSource(c),
        c.pendantReconnectInFlight,
      ),
    );
    return LiveEpisodeClock(
      clock: episodes.now,
      builder: (context, now) => _row(context, episodes, context.read<CaptureProvider>(), state, now, reconnecting),
    );
  }

  Widget _row(
    BuildContext context,
    EpisodeProvider episodes,
    CaptureProvider capture,
    CaptureDisplayState state,
    DateTime now,
    bool reconnecting,
  ) {
    final l10n = context.l10n;
    final episode = episodes.live;
    final listening = EpisodePresentation.isListening(state);
    final running = EpisodePresentation.elapsed(episode, capture, now, anchor: episodes.liveAnchor);
    // The same session duration the episode page counts; the page shows its seconds, the
    // tile its whole minutes, and the spoken label carries the page's form.
    final elapsed = EpisodePresentation.runningLength(running, l10n);
    final named = (episode?.title ?? '').trim();
    // A pendant whose recovery was exhausted owes audio: the row names the failure
    // and offers the one action that can fix it — never Listening, and no topic of
    // its own to headline over it.
    final noAudio = state == CaptureDisplayState.noAudio;
    final title = noAudio ? l10n.captureNoAudioFromPendant : (named.isEmpty ? l10n.episodeListeningNow : named);
    final topics = noAudio || named.isNotEmpty ? '' : EpisodePresentation.topics(episode);
    final peopleNamed = noAudio ? 0 : _peopleCount(capture);
    // A local-preview session reads its newest on-device words on line two, trimmed at the
    // start so the latest words stay visible, for the whole session: words the final
    // transcript already covers drop out, the rest stay. The duration lives in the tile.
    final preview = listening && capture.localPreviewAdmitted ? capture.livePreview : null;
    String previewText() => preview == null
        ? ''
        : _previewTail(LivePreviewCoverage.uncovered(preview.lines, capture.segments, capture.liveTranscriptStartedAt));
    final status = noAudio
        ? l10n.captureNoAudioDetail
        : listening
            ? null
            : captureStateLabel(l10n, state);
    final details = [
      if (status != null) status,
      if (peopleNamed >= 2) l10n.peopleCount(peopleNamed),
      if (topics.isNotEmpty) topics,
    ];
    // Line two without preview text is today's subtitle minus the duration the tile now
    // carries; a bare live row with nothing else to say still says it is live.
    final rest = details.isEmpty ? l10n.live : details.join(' · ');
    final subtitleStyle = OmiType.subhead.copyWith(color: noAudio ? OmiColors.warning : OmiColors.textTertiary);

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

    void reconnect() {
      OmiHaptics.medium();
      final message = l10n.somethingWentWrong;
      capture.reconnectRecordingPendant().catchError((Object error) {
        // A pendant that vanished under the tap is not the reader's problem to
        // debug; anything else already rebuilt the row.
        if (mounted) AppSnackbar.showSnackbar(message);
      });
    }

    return Padding(
      padding: const EdgeInsets.only(top: 8, left: 16, right: 16),
      child: CaptureStateAnnouncement(
        message: listening ? l10n.episodeListeningNow : captureStateLabel(l10n, state),
        child: Semantics(
          key: const Key('home_live_episode_semantics'),
          button: true,
          label: [
            title,
            if (listening) (episode == null ? l10n.episodeCaptureFor : l10n.episodeLiveFor)(elapsed),
            previewText().isNotEmpty ? previewText() : rest,
          ].join(', '),
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
                    _DurationTile(
                      live: listening,
                      warning: noAudio,
                      duration: listening ? _tileLength(running, l10n) : null,
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            title,
                            style: Theme.of(context)
                                .textTheme
                                .titleMedium
                                ?.copyWith(color: noAudio ? OmiColors.warning : null),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                          const SizedBox(height: 3),
                          // Words land as the recognizer hears them, not on the clock's tick.
                          ListenableBuilder(
                            listenable: preview ?? const AlwaysStoppedAnimation<double>(0),
                            builder: (context, _) {
                              final text = previewText();
                              return text.isNotEmpty
                                  ? StartTrimmedText(
                                      key: const Key('home_live_episode_preview'),
                                      runs: [(text: text, style: null)],
                                      style: subtitleStyle,
                                      // At accessibility sizes one line holds a word or two; a
                                      // second keeps the newest words readable.
                                      maxLines: MediaQuery.textScalerOf(context).scale(10) > 16 ? 2 : 1,
                                    )
                                  : Text(rest, style: subtitleStyle, maxLines: 1, overflow: TextOverflow.ellipsis);
                            },
                          ),
                        ],
                      ),
                    ),
                    if (noAudio)
                      OmiButton.secondary(
                        key: const Key('home_live_episode_reconnect'),
                        label: l10n.reconnect,
                        // Null while a reconnect runs: the controller ignores taps
                        // meanwhile, and the row shows it.
                        onPressed: reconnecting ? null : reconnect,
                        size: OmiButtonSize.compact,
                      )
                    else
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

  /// The newest preview words, a few lines' worth: enough to fill one trimmed line.
  static String _previewTail(List<LivePreviewLine> lines) {
    final tail = <String>[];
    var length = 0;
    for (final line in lines.reversed) {
      final text = line.text.trim();
      if (text.isEmpty) continue;
      tail.insert(0, text);
      length += text.length;
      if (length > 160) break;
    }
    return tail.join(' ');
  }

  /// The tile's coarse length: seconds for the first minute, then whole minutes, then hours.
  static String _tileLength(Duration running, AppLocalizations l10n) {
    final total = running.inSeconds;
    if (total < 60) return l10n.timeCompactSecs(total);
    final minutes = running.inMinutes;
    if (minutes < 60) return l10n.timeCompactMins(minutes);
    final rest = minutes % 60;
    return rest == 0 ? l10n.timeCompactHours(minutes ~/ 60) : l10n.timeCompactHoursAndMins(minutes ~/ 60, rest);
  }
}

/// The live row's outlined tile: the running length alone, in ink, no colour (David, 10-27: no dot).
/// Before a length exists it holds the breathing dot.
class _DurationTile extends StatelessWidget {
  const _DurationTile({required this.live, required this.warning, required this.duration});

  final bool live;
  final bool warning;
  final String? duration;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 36,
      height: 36,
      alignment: Alignment.center,
      padding: const EdgeInsets.symmetric(horizontal: 2),
      decoration: BoxDecoration(
        borderRadius: OmiRadius.mdAll,
        border: Border.all(color: warning ? OmiColors.warning : OmiColors.border),
      ),
      child: duration == null
          ? OmiBreathingDot(live: live)
          // Scaled down, never clipped: an hour-long "1h 12m" or a large text size still fits.
          : FittedBox(
              fit: BoxFit.scaleDown,
              child: Text(
                duration!,
                key: const Key('home_live_episode_duration'),
                maxLines: 1,
                textScaler: TextScaler.noScaling,
                style: OmiType.footnote.copyWith(
                  fontWeight: FontWeight.w600,
                  height: 1,
                  fontFeatures: const [FontFeature.tabularFigures()],
                ),
              ),
            ),
    );
  }
}
