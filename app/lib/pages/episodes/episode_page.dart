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

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void didUpdateWidget(EpisodePage oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.episode.id != widget.episode.id) {
      _detail = null;
      unawaited(_load());
    }
  }

  Future<void> _load() async {
    final generation = ++_generation;
    final enabled = await EpisodeDetailGate.enabled(readFlag: widget.readFlag);
    if (!mounted || generation != _generation) return;
    setState(() => _redesigned = enabled);
    if (!enabled || widget.episode.id.isEmpty) return;
    final result =
        await (widget.loadDetail ?? context.read<EpisodeProvider?>()?.detailFor ?? api.getEpisode)(widget.episode.id);
    if (!mounted || generation != _generation) return;
    if (result case ApiSuccess<Episode>(:final data)) setState(() => _detail = data);
    // An older/offline server retains the opening snapshot and normal row navigation.
  }

  @override
  Widget build(BuildContext context) => EpisodePageContent(
        episode: _detail ?? widget.episode,
        detailMembers: _redesigned ? _detail?.members : null,
        redesigned: _redesigned,
      );
}
