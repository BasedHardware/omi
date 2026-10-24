import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/http/api/conversations.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/pages/conversation_detail/page.dart';
import 'package:omi/providers/capture_provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/other/temp.dart';

/// Kept outside the history query: an idle-closed episode's member may still be in_progress.
class PreviousEpisodeLink extends StatefulWidget {
  const PreviousEpisodeLink({super.key, this.onOpenConversation});

  final ValueChanged<String>? onOpenConversation;

  @override
  State<PreviousEpisodeLink> createState() => _PreviousEpisodeLinkState();
}

class _PreviousEpisodeLinkState extends State<PreviousEpisodeLink> {
  EpisodeProvider? _episodes;
  String? _conversationId;

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
    final id = context.select<CaptureProvider, String?>((c) => c.topConversationId);
    final episodes = context.watch<EpisodeProvider?>();
    // A current episode already identifies this capture. Only recover through its member
    // when the live endpoint is empty; a later disappearance re-arms this lookup.
    if (id != _conversationId && episodes?.live == null) {
      _conversationId = id;
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && id != null) unawaited(_episodes?.recoverPrevious(id));
      });
    }
    final episode = episodes?.previous;
    if (episode == null) return const SizedBox.shrink();
    return Padding(
      padding: const EdgeInsets.all(OmiSpacing.md),
      child: OmiButton.tertiary(
        key: const Key('previous_episode_link'),
        label:
            '${context.l10n.episodeOpenPrevious}: ${episode.title.trim().isEmpty ? context.l10n.conversationTab : episode.title}',
        onPressed: () =>
            routeToPage(context, PreviousEpisodePage(episode: episode, onOpenConversation: widget.onOpenConversation)),
      ),
    );
  }
}

/// Keep the retained snapshot readable while closure and member finalization catch up.
class PreviousEpisodePage extends StatefulWidget {
  const PreviousEpisodePage({super.key, required this.episode, this.onOpenConversation});

  final Episode episode;
  final ValueChanged<String>? onOpenConversation;

  @override
  State<PreviousEpisodePage> createState() => _PreviousEpisodePageState();
}

class _PreviousEpisodePageState extends State<PreviousEpisodePage> {
  EpisodeProvider? _episodes;
  Timer? _refresh;

  String? get _memberId =>
      widget.episode.conversationIds.lastOrNull ?? widget.episode.moments.lastOrNull?.conversationId;

  @override
  void initState() {
    super.initState();
    _episodes = context.read<EpisodeProvider?>();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted) _recover();
    });
    _refresh = Timer.periodic(EpisodeProvider.pollInterval, (_) => _recover());
  }

  void _recover() {
    if (!mounted || ModalRoute.of(context)?.isCurrent == false) return;
    final id = _memberId;
    if (id != null) unawaited(_episodes?.recoverPrevious(id));
  }

  @override
  void dispose() {
    _refresh?.cancel();
    super.dispose();
  }

  Future<void> _open(BuildContext context, String id) async {
    if (widget.onOpenConversation != null) {
      widget.onOpenConversation!(id);
      return;
    }
    final conversation = await getConversationById(id);
    if (!context.mounted) return;
    if (conversation == null) {
      OmiFeedback.info(context, context.l10n.somethingWentWrongTryAgain);
      return;
    }
    routeToPage(context, ConversationDetailPage(conversation: conversation));
  }

  @override
  Widget build(BuildContext context) {
    final episodes = context.watch<EpisodeProvider?>();
    final cached = _memberId == null ? null : episodes?.cachedEpisodeFor(_memberId!);
    final previous = episodes?.previous;
    final episode = previous?.id == widget.episode.id
        ? previous!
        : cached?.id == widget.episode.id
            ? cached!
            : widget.episode;
    final dates = OmiDateFormat.of(context);
    final ids = {...episode.conversationIds, ...episode.moments.map((m) => m.conversationId)};
    return Scaffold(
      key: const Key('previous_episode_page'),
      appBar: AppBar(
        automaticallyImplyLeading: false,
        leading: const Center(child: OmiBackButton()),
        title: Text(context.l10n.episodePrevious),
      ),
      body: ListView(
        padding: const EdgeInsets.all(OmiSpacing.md),
        children: [
          Text(episode.title, style: OmiType.title1),
          Text('${dates.dayHeader(episode.startedAt)} · ${dates.time(episode.startedAt)}', style: OmiType.subhead),
          const SizedBox(height: OmiSpacing.md),
          for (final bullet in episode.bullets)
            Padding(
              padding: const EdgeInsets.only(bottom: OmiSpacing.sm),
              child: Text(bullet, style: OmiType.body),
            ),
          if (episode.moments.isNotEmpty) ...[
            Text(context.l10n.episodeMoments, style: OmiType.headline),
            for (final moment in episode.moments)
              Padding(
                padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
                child: Text('${dates.time(moment.startedAt)} · ${moment.heading}', style: OmiType.callout),
              ),
          ],
          for (final id in ids)
            OmiButton.tertiary(
              key: ValueKey('previous_episode_conversation_$id'),
              label: context.l10n.openConversation,
              onPressed: () => _open(context, id),
            ),
        ],
      ),
    );
  }
}
