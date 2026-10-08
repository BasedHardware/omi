part of 'conversation_bottom_bar.dart';

extension _NativePlaybackPresentation on _ConversationBottomBarState {
  void _publishNativePresentation() {
    if (!mounted || widget.onNativePresentation == null || _nativePresentationScheduled) return;
    _nativePresentationScheduled = true;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _nativePresentationScheduled = false;
      if (!mounted || widget.onNativePresentation == null) return;
      final l10n = context.l10n;
      final controller = widget.playbackController;
      final hasAudio = widget.conversation?.hasAudio() ?? false;
      final wallEnd = _wallEndSeconds;
      final unmapped = _isAudioInitialized && _timelineMapper == null;
      final position = Duration(milliseconds: (_artifactPosition.value * 1000).toInt());
      final status = switch ((_failure, _showPreparingLabel)) {
        (_AudioFailure.transport, _) => l10n.playbackAudioNetworkFailed,
        (_AudioFailure.unavailable, _) || (_AudioFailure.unmappable, _) => l10n.playbackAudioUnavailable,
        (_AudioFailure.loadFailed, _) => l10n.playbackAudioLoadFailed,
        (null, true) => _readyParts < _totalParts
            ? '${l10n.playbackPreparingAudio} $_readyParts/$_totalParts'
            : l10n.playbackPreparingAudio,
        _ when _hasUnplaceableMissing => l10n.playbackAudioUnavailable,
        _ => '-${_formatDurationRemaining(position)}',
      };
      final levels = speechLevels(widget.conversation?.transcriptSegments ?? const [], _waveformBars,
          start: 0, end: wallEnd > 0 ? wallEnd : null);
      widget.onNativePresentation!([
        if (hasAudio && widget.selectedTab == ConversationTab.transcript) ...[
          NativeRow('detail_audio_play', _effectivePlaying ? l10n.pause : l10n.play,
              symbol: _effectivePlaying ? 'pause.fill' : 'play.fill',
              enabled: !_isAudioLoading,
              action: (_) => _togglePlayPause()),
          if (wallEnd > 0)
            NativeRow('detail_audio_position', l10n.recordings,
                kind: 'slider',
                value: unmapped ? 0.0 : (controller?.wallPosition.value ?? 0).clamp(0.0, wallEnd),
                maximumValue: wallEnd,
                subtitle: status,
                points: [
                  for (var i = 0; i < levels.length; i++)
                    {
                      'x': (i + 0.5) / levels.length * wallEnd,
                      'y': levels[i],
                      'label': _missingRanges.any((range) =>
                                  (i + 0.5) / levels.length >= range.$1 && (i + 0.5) / levels.length < range.$2) ||
                              _hasUnplaceableMissing
                          ? 'missing'
                          : '',
                    },
                ], action: (value) {
              widget.onAudioInteraction?.call();
              controller?.seek((value as num).toDouble());
            }),
          if (wallEnd <= 0) NativeRow('detail_audio_status', status, kind: 'label'),
          if (_failure != null && _failure != _AudioFailure.unmappable)
            NativeRow('detail_audio_retry', l10n.tryAgain, action: (_) => _retryAudio()),
          if (controller != null &&
              !controller.isFollowing &&
              controller.followTargetSegmentId != null &&
              _isAudioInitialized)
            NativeRow('detail_audio_follow', l10n.playbackBackToCurrent, action: (_) => controller.backToCurrent()),
        ],
        NativeRow('detail_ask_omi', l10n.askOmi, symbol: 'bubble.left.and.bubble.right', action: (_) => _askOmi()),
      ]);
    });
    WidgetsBinding.instance.ensureVisualUpdate();
  }
}
