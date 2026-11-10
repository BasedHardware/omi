// Episode detail route owns the operational gate and full member refresh.
// Existing content remains available when an older or offline server cannot refresh.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:omi/providers/episode_provider.dart';
import 'package:omi/backend/http/api/episodes.dart' as api;
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/episode.dart';
import 'package:omi/pages/episodes/episode_page_content.dart';
import 'package:omi/services/experiments/episode_detail_gate.dart';

/// Retains the opening snapshot while refreshing the full retained member payload.
class EpisodePage extends StatefulWidget {
  const EpisodePage({super.key, required this.episode, this.readFlag, this.loadDetail});

  final Episode episode;
  final Future<bool> Function(String)? readFlag;
  final Future<ApiResult<Episode>> Function(String)? loadDetail;

  @override
  State<EpisodePage> createState() => _EpisodePageState();
}

class _EpisodePageState extends State<EpisodePage> {
  bool _redesigned = true;
  Episode? _detail;
  int _generation = 0;
  late final Future<bool> _gate;
  (String, DateTime?, bool)? _requested;

  @override
  void initState() {
    super.initState();
    _gate = EpisodeDetailGate.enabled(readFlag: widget.readFlag);
  }

  void _refresh((String, DateTime?, bool) key) {
    if (_requested == key) return;
    _requested = key;
    if (_detail?.id != key.$1) _detail = null;
    unawaited(_load(key.$1));
  }

  Future<void> _load(String episodeId) async {
    final generation = ++_generation;
    final enabled = await _gate;
    if (!mounted || generation != _generation) return;
    setState(() => _redesigned = enabled);
    if (!enabled || episodeId.isEmpty) return;
    final result =
        await (widget.loadDetail ?? context.read<EpisodeProvider?>()?.detailFor ?? api.getEpisode)(episodeId);
    if (!mounted || generation != _generation) return;
    if (result case ApiSuccess<Episode>(:final data)) setState(() => _detail = data);
    // An older/offline server retains the opening snapshot and normal row navigation.
  }

  @override
  Widget build(BuildContext context) {
    final revision = context.select<EpisodeProvider?, (String, DateTime?, bool)>((episodes) {
      final opened = widget.episode;
      final current = episodes?.homeEpisodes
              .where(
                  (e) => opened.id.isEmpty ? e.conversationIds.any(opened.conversationIds.contains) : e.id == opened.id)
              .firstOrNull ??
          opened;
      return (current.id, current.stateUpdatedAt, current.composed);
    });
    _refresh(revision);
    return EpisodePageContent(
      episode: _detail ?? widget.episode,
      detailMembers: _redesigned ? _detail?.members : null,
      redesigned: _redesigned,
    );
  }
}
