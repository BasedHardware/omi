import 'dart:async';
import 'dart:math' as math;

import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/providers/device_onboarding_provider.dart';
import 'package:omi/services/voice_playback/omi_voice_playback_service.dart';
import 'package:omi/services/voice_playback/voice_output_route.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/analytics/analytics_manager.dart';
import 'package:omi/utils/l10n_extensions.dart';

class VoiceReplyStep extends StatefulWidget {
  const VoiceReplyStep({
    super.key,
    required this.onComplete,
    required this.firstRun,
    this.previewText,
    this.outputRouteSource,
    this.playPreview,
    this.stopPreview,
    this.onModeAnalytics,
    this.preferences,
  });

  final VoidCallback onComplete;
  final bool firstRun;
  final String? previewText;
  final VoiceOutputRouteSource? outputRouteSource;
  final Future<void> Function(String text)? playPreview;
  final Future<void> Function()? stopPreview;
  final ValueChanged<int>? onModeAnalytics;
  final SharedPreferencesUtil? preferences;

  @override
  State<VoiceReplyStep> createState() => _VoiceReplyStepState();
}

class _VoiceReplyStepState extends State<VoiceReplyStep> with SingleTickerProviderStateMixin {
  late final SharedPreferencesUtil _preferences;
  late final VoiceOutputRouteSource _outputRouteSource;
  late final AnimationController _waveController;
  StreamSubscription<VoiceOutputRoute>? _routeSubscription;
  VoiceOutputRoute _route = const VoiceOutputRoute.unknown();
  bool _playing = false;

  DeviceOnboardingProvider get _provider => context.read<DeviceOnboardingProvider>();

  @override
  void initState() {
    super.initState();
    _preferences = widget.preferences ?? SharedPreferencesUtil();
    _outputRouteSource = widget.outputRouteSource ?? AudioSessionVoiceOutputRouteSource();
    _waveController = AnimationController(vsync: this, duration: const Duration(milliseconds: 900));

    final initialized = _provider.initializeVoiceResponseMode(
      firstRun: widget.firstRun,
      currentPreference: _preferences.voiceResponseMode,
    );
    if (initialized && widget.firstRun) {
      _preferences.voiceResponseMode = 0;
    }

    _routeSubscription = _outputRouteSource.watch().listen((route) {
      if (mounted) setState(() => _route = route);
    });
  }

  @override
  void dispose() {
    _routeSubscription?.cancel();
    _waveController.dispose();
    unawaited((widget.stopPreview ?? OmiVoicePlaybackService.instance.stopPreview)());
    super.dispose();
  }

  Future<void> _togglePreview() async {
    if (_playing) {
      setState(() => _playing = false);
      _waveController.stop();
      await (widget.stopPreview ?? OmiVoicePlaybackService.instance.stopPreview)();
      return;
    }

    final text = widget.previewText?.trim();
    final previewText = text == null || text.isEmpty ? context.l10n.deviceOnboardingVoiceReplySample : text;
    setState(() => _playing = true);
    if (!(MediaQuery.maybeDisableAnimationsOf(context) ?? false)) {
      _waveController.repeat();
    }
    await OmiHaptics.light();
    try {
      await (widget.playPreview ?? OmiVoicePlaybackService.instance.playPreview)(previewText);
    } finally {
      if (mounted) {
        _waveController.stop();
        setState(() => _playing = false);
      }
    }
  }

  void _selectMode(int mode) {
    if (_provider.selectedVoiceResponseMode == mode) return;
    _provider.selectVoiceResponseMode(mode);
    _preferences.voiceResponseMode = mode;
    (widget.onModeAnalytics ?? AnalyticsManager().voiceResponseModeChanged)(mode);
    unawaited(OmiHaptics.selection());
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceOnboardingProvider>(builder: (context, provider, _) {
      final mode = provider.selectedVoiceResponseMode ?? 0;
      return Padding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.lg),
        child: Column(
          children: [
            const SizedBox(height: OmiSpacing.lg),
            Text(context.l10n.deviceOnboardingVoiceReplyTitle, style: OmiType.title1, textAlign: TextAlign.center),
            const SizedBox(height: OmiSpacing.xs),
            Text(
              context.l10n.voiceResponseAudio,
              style: OmiType.callout.copyWith(color: OmiColors.textSecondary, height: 1.35),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: OmiSpacing.lg),
            Expanded(
              child: SingleChildScrollView(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [
                    _PreviewCard(
                      playing: _playing,
                      animation: _waveController,
                      onPressed: _togglePreview,
                    ),
                    const SizedBox(height: OmiSpacing.lg),
                    Text(
                      context.l10n.voiceResponseModeTitle.toUpperCase(),
                      style: OmiType.footnote.copyWith(
                        color: OmiColors.textSecondary,
                        fontWeight: FontWeight.w600,
                        letterSpacing: 0.6,
                      ),
                    ),
                    const SizedBox(height: OmiSpacing.xs),
                    _ModeCard(
                      key: const Key('voice_reply_mode_off'),
                      selected: mode == 0,
                      title: context.l10n.voiceResponseOff,
                      onTap: () => _selectMode(0),
                    ),
                    const SizedBox(height: OmiSpacing.xs),
                    _ModeCard(
                      key: const Key('voice_reply_mode_headphones'),
                      selected: mode == 1,
                      title: context.l10n.voiceResponseHeadphonesOnly,
                      onTap: () => _selectMode(1),
                    ),
                    const SizedBox(height: OmiSpacing.xs),
                    _ModeCard(
                      key: const Key('voice_reply_mode_always'),
                      selected: mode == 2,
                      title: context.l10n.voiceResponseAlways,
                      onTap: () => _selectMode(2),
                    ),
                    const SizedBox(height: OmiSpacing.sm),
                    _OutputStatus(mode: mode, route: _route),
                  ],
                ),
              ),
            ),
            const SizedBox(height: OmiSpacing.sm),
            Text(
              '${context.l10n.settings} › ${context.l10n.voiceResponseMode}',
              style: OmiType.footnote.copyWith(color: OmiColors.textSecondary),
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: OmiSpacing.sm),
            OmiButton(
              key: const Key('voice_reply_continue'),
              label: context.l10n.deviceOnboardingContinue,
              onPressed: widget.onComplete,
              expand: true,
              labelStyle: OmiType.callout.copyWith(fontWeight: FontWeight.w600, fontFamily: 'Roboto'),
            ),
            const SizedBox(height: OmiSpacing.lg),
          ],
        ),
      );
    });
  }
}

class _PreviewCard extends StatelessWidget {
  const _PreviewCard({required this.playing, required this.animation, required this.onPressed});

  final bool playing;
  final Animation<double> animation;
  final Future<void> Function() onPressed;

  @override
  Widget build(BuildContext context) {
    final semanticsLabel = playing ? context.l10n.stop : context.l10n.play;
    return Container(
      key: const Key('voice_reply_preview_card'),
      padding: const EdgeInsets.all(OmiSpacing.sm),
      decoration: const BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
      child: Row(
        children: [
          Semantics(
            button: true,
            label: semanticsLabel,
            child: Material(
              color: OmiColors.accent,
              shape: const CircleBorder(),
              child: InkWell(
                key: const Key('voice_reply_preview_button'),
                onTap: onPressed,
                customBorder: const CircleBorder(),
                child: SizedBox(
                  width: 48,
                  height: 48,
                  child: Icon(playing ? Icons.stop_rounded : Icons.play_arrow_rounded, color: OmiColors.onAccent),
                ),
              ),
            ),
          ),
          const SizedBox(width: OmiSpacing.sm),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                AnimatedSwitcher(
                  duration: OmiMotion.of(context).quick,
                  child: Text(
                    playing ? context.l10n.stop : context.l10n.voiceResponseAudio,
                    key: ValueKey(playing),
                    style: OmiType.subhead.copyWith(fontWeight: FontWeight.w600),
                  ),
                ),
                const SizedBox(height: OmiSpacing.xs),
                SizedBox(
                  height: 18,
                  child: AnimatedBuilder(
                    animation: animation,
                    builder: (context, _) => CustomPaint(
                      key: const Key('voice_reply_waveform'),
                      painter: _VoiceWaveformPainter(phase: playing ? animation.value : 0),
                      size: const Size(double.infinity, 18),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _ModeCard extends StatelessWidget {
  const _ModeCard({
    super.key,
    required this.selected,
    required this.title,
    required this.onTap,
  });

  final bool selected;
  final String title;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final foreground = selected ? OmiColors.onAccent : OmiColors.textPrimary;
    return Semantics(
      button: true,
      selected: selected,
      child: Material(
        color: selected ? OmiColors.accent : OmiColors.surface1,
        shape: RoundedRectangleBorder(
          borderRadius: OmiRadius.lgAll,
          side: BorderSide(color: selected ? OmiColors.accent : OmiColors.border),
        ),
        child: InkWell(
          onTap: onTap,
          borderRadius: OmiRadius.lgAll,
          child: ConstrainedBox(
            constraints: const BoxConstraints(minHeight: 64),
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.md, vertical: OmiSpacing.sm),
              child: Row(
                children: [
                  Container(
                    width: 22,
                    height: 22,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      border: Border.all(color: selected ? OmiColors.onAccent : OmiColors.textTertiary, width: 2),
                    ),
                    alignment: Alignment.center,
                    child: AnimatedContainer(
                      duration: OmiMotion.of(context).quick,
                      width: selected ? 10 : 0,
                      height: selected ? 10 : 0,
                      decoration: const BoxDecoration(shape: BoxShape.circle, color: OmiColors.onAccent),
                    ),
                  ),
                  const SizedBox(width: OmiSpacing.sm),
                  Expanded(
                    child: Text(
                      title,
                      style: OmiType.callout.copyWith(color: foreground, fontWeight: FontWeight.w600),
                    ),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

class _OutputStatus extends StatelessWidget {
  const _OutputStatus({required this.mode, required this.route});

  final int mode;
  final VoiceOutputRoute route;

  @override
  Widget build(BuildContext context) {
    final (:text, :tone, :surface, :icon) = _content(context);
    return Semantics(
      liveRegion: true,
      child: AnimatedContainer(
        key: const Key('voice_reply_output_status'),
        duration: OmiMotion.of(context).standard,
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.sm, vertical: OmiSpacing.sm),
        decoration: BoxDecoration(color: surface, borderRadius: OmiRadius.mdAll),
        child: Row(
          children: [
            Icon(icon, size: 20, color: tone),
            const SizedBox(width: OmiSpacing.xs),
            Expanded(child: Text(text, style: OmiType.footnote.copyWith(color: tone, height: 1.3))),
          ],
        ),
      ),
    );
  }

  ({String text, Color tone, Color surface, IconData icon}) _content(BuildContext context) {
    if (mode == 0) {
      return (
        text: context.l10n.voiceResponseOff,
        tone: OmiColors.textSecondary,
        surface: OmiColors.surface1,
        icon: Icons.volume_off_outlined,
      );
    }

    final routeName =
        route.name == null || route.name!.isEmpty ? context.l10n.voiceResponseHeadphonesOnly : route.name!;
    if (mode == 1) {
      return switch (route.kind) {
        VoiceOutputRouteKind.headphones => (
            text: '$routeName · ${context.l10n.connected}',
            tone: OmiColors.success,
            surface: OmiColors.successSurface,
            icon: Icons.headphones,
          ),
        VoiceOutputRouteKind.speaker => (
            text: '${context.l10n.voiceResponseHeadphonesOnly} · ${context.l10n.disconnected}',
            tone: OmiColors.warning,
            surface: OmiColors.surface1,
            icon: Icons.headset_off_outlined,
          ),
        VoiceOutputRouteKind.unknown => (
            text: '${context.l10n.audioOutput} · ${context.l10n.disconnected}',
            tone: OmiColors.warning,
            surface: OmiColors.surface1,
            icon: Icons.help_outline,
          ),
      };
    }

    return switch (route.kind) {
      VoiceOutputRouteKind.headphones => (
          text: '$routeName · ${context.l10n.connected}',
          tone: OmiColors.success,
          surface: OmiColors.successSurface,
          icon: Icons.headphones,
        ),
      VoiceOutputRouteKind.speaker => (
          text: '${context.l10n.phoneSpeaker} · ${context.l10n.connected}',
          tone: OmiColors.warning,
          surface: OmiColors.surface1,
          icon: Icons.volume_up_outlined,
        ),
      VoiceOutputRouteKind.unknown => (
          text: context.l10n.audioOutput,
          tone: OmiColors.textSecondary,
          surface: OmiColors.surface1,
          icon: Icons.speaker_outlined,
        ),
    };
  }
}

class _VoiceWaveformPainter extends CustomPainter {
  const _VoiceWaveformPainter({required this.phase});

  final double phase;

  @override
  void paint(Canvas canvas, Size size) {
    const bars = 18;
    const gap = 3.0;
    final width = (size.width - gap * (bars - 1)) / bars;
    final paint = Paint()..color = OmiColors.textPrimary.withValues(alpha: phase == 0 ? 0.35 : 0.9);
    for (var index = 0; index < bars; index++) {
      final base = 0.3 + ((index * 7) % 11) / 16;
      final pulse = phase == 0 ? 1.0 : 0.55 + 0.45 * math.sin((phase * math.pi * 2) + index * 0.72).abs();
      final height = size.height * base * pulse;
      final left = index * (width + gap);
      final top = (size.height - height) / 2;
      canvas.drawRRect(
        RRect.fromRectAndRadius(Rect.fromLTWH(left, top, width, height), const Radius.circular(2)),
        paint,
      );
    }
  }

  @override
  bool shouldRepaint(covariant _VoiceWaveformPainter oldDelegate) => oldDelegate.phase != phase;
}
