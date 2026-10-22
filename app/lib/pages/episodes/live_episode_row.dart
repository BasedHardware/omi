import 'package:flutter/material.dart';

import 'package:provider/provider.dart';

import 'package:omi/pages/conversations/capture_state_labels.dart';
import 'package:omi/pages/episodes/episode_presentation.dart';
import 'package:omi/pages/episodes/live_episode_clock.dart';
import 'package:omi/pages/episodes/live_episode_page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';
import 'package:omi/utils/platform/platform_manager.dart';

/// Home's live episode: the first row of Today, drawn like any conversation row. A green,
/// pulsing tile, the episode's title, and "Now · 24m · lunch plans, git support". It scrolls with
/// the list; there is no overlay and nothing sticks to the header. Opens the live episode.
class LiveEpisodeRow extends StatefulWidget {
  const LiveEpisodeRow({super.key});

  @override
  State<LiveEpisodeRow> createState() => _LiveEpisodeRowState();
}

class _LiveEpisodeRowState extends State<LiveEpisodeRow> {
  EpisodeProvider? _episodes;

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
    final elapsed = EpisodePresentation.runningLength(
      EpisodePresentation.elapsed(episode, capture, now, anchor: episodes.liveAnchor),
      l10n,
    );
    final title = (episode?.title ?? '').trim().isEmpty ? l10n.episodeListeningNow : episode!.title;
    final topics = EpisodePresentation.topics(episode);
    final status = listening ? l10n.episodeNow : captureStateLabel(l10n, state);
    final rest = [elapsed, if (topics.isNotEmpty) topics].join(' · ');
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
      child: Semantics(
        button: true,
        liveRegion: true,
        label: '$title, $status · $rest',
        onTap: open,
        excludeSemantics: true,
        child: Material(
          key: const Key('home_live_episode_row'),
          color: OmiColors.surface1,
          borderRadius: OmiRadius.xlAll,
          child: InkWell(
            borderRadius: OmiRadius.xlAll,
            onTap: open,
            child: Padding(
              padding: const EdgeInsetsDirectional.fromSTEB(14, 14, 10, 14),
              child: Row(
                children: [
                  EpisodePresentation.liveTile(listening: listening, size: 36),
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
                        Text.rich(
                          TextSpan(
                            children: [
                              TextSpan(
                                text: status,
                                style: TextStyle(color: listening ? OmiColors.success : OmiColors.textSecondary),
                              ),
                              TextSpan(text: ' · $rest'),
                            ],
                          ),
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
    );
  }
}
