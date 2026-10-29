import 'package:flutter/material.dart';
import 'package:permission_handler/permission_handler.dart';

import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/services/live_preview/live_preview_engine.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The live transcript surface for a local-preview session: final transcript
/// segments first (when any arrived), then the "Live on this phone" divider,
/// then the preview lines it does not already cover — provisional, on-device
/// text that the batch transcript replaces. Words the recognizer may still
/// revise are drawn in secondary text; settled words in primary text. No
/// speaker labels: preview text has no speaker attribution.
///
/// With no on-device engine it is a calm card ("Recording safely"), not an
/// error and not a setup prompt, with a settings link only where the platform
/// can deep-link to its speech settings.
class LivePreviewTranscript extends StatelessWidget {
  const LivePreviewTranscript({super.key, required this.preview, this.bottomInset = 84});

  final LivePreviewController preview;

  /// Room kept clear below the newest line for the page's floating controls.
  final double bottomInset;

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: preview,
      builder: (context, _) => switch (preview.phase) {
        LivePreviewPhase.unavailable => _NoEngine(reason: preview.selected?.reason),
        LivePreviewPhase.starting => _Waiting(text: context.l10n.livePreviewStarting),
        _ => preview.lines.isEmpty
            ? _Waiting(text: context.l10n.livePreviewListening, spinner: false)
            : _Lines(lines: preview.lines, bottomInset: bottomInset),
      },
    );
  }
}

class _Lines extends StatefulWidget {
  const _Lines({required this.lines, required this.bottomInset});

  final List<LivePreviewLine> lines;
  final double bottomInset;

  @override
  State<_Lines> createState() => _LinesState();
}

/// Reads top-down and follows the newest words while the reader is at the
/// bottom; scrolling up to reread stops the follow until they return.
class _LinesState extends State<_Lines> {
  final ScrollController _scroll = ScrollController();
  bool _following = true;

  @override
  void initState() {
    super.initState();
    _scroll.addListener(() {
      final position = _scroll.position;
      _following = position.pixels >= position.maxScrollExtent - 48;
    });
  }

  @override
  void didUpdateWidget(covariant _Lines oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (!_following) return;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (mounted && _scroll.hasClients) _scroll.jumpTo(_scroll.position.maxScrollExtent);
    });
  }

  @override
  void dispose() {
    _scroll.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final lines = widget.lines;
    return ListView.builder(
      controller: _scroll,
      padding: EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xs, OmiSpacing.md,
          MediaQuery.paddingOf(context).bottom + widget.bottomInset + OmiSpacing.md),
      itemCount: lines.length,
      itemBuilder: (context, index) {
        final line = lines[index];
        return Padding(
          key: ValueKey('live_preview_line_${line.id}'),
          padding: const EdgeInsets.only(bottom: OmiSpacing.sm),
          child: Text(
            line.text,
            style: OmiType.body.copyWith(
              height: 1.4,
              color: line.isFinal ? OmiColors.textPrimary : OmiColors.textSecondary,
            ),
          ),
        );
      },
    );
  }
}

class _Waiting extends StatelessWidget {
  const _Waiting({required this.text, this.spinner = true});

  final String text;
  final bool spinner;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (spinner) ...[
              const OmiSpinner(size: OmiSpinnerSize.small),
              const SizedBox(height: OmiSpacing.sm),
            ],
            Text(
              text,
              textAlign: TextAlign.center,
              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
            ),
          ],
        ),
      ),
    );
  }
}

/// Admitted, but this phone has no on-device engine: the mic glyph card that
/// says when words arrive and — only where the platform can deep-link to its
/// speech settings (a denied speech permission is the one case both platforms
/// can open) — the link that turns live text on.
class _NoEngine extends StatelessWidget {
  const _NoEngine({this.reason});

  final LivePreviewReason? reason;

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final canOpenSpeechSettings = reason == LivePreviewReason.speechPermissionDenied;
    // A calm card at the top of the tab, where the transcript will start: not an error, not
    // a setup prompt.
    return Align(
      key: const Key('live_preview_no_engine'),
      alignment: Alignment.topCenter,
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.md, OmiSpacing.md, OmiSpacing.md),
        child: Container(
          width: double.infinity,
          padding: const EdgeInsets.fromLTRB(OmiSpacing.lg, OmiSpacing.xl, OmiSpacing.lg, OmiSpacing.lg),
          decoration: BoxDecoration(color: OmiColors.surface1, borderRadius: OmiRadius.lgAll),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.mic_none_rounded, size: 32, color: OmiColors.textTertiary),
              const SizedBox(height: OmiSpacing.sm),
              Text(l10n.livePreviewNoEngineTitle, textAlign: TextAlign.center, style: OmiType.headline),
              const SizedBox(height: OmiSpacing.xs),
              Text(
                l10n.livePreviewNoEngineBody,
                textAlign: TextAlign.center,
                style: OmiType.subhead.copyWith(color: OmiColors.textSecondary, height: 1.45),
              ),
              if (canOpenSpeechSettings) ...[
                const SizedBox(height: OmiSpacing.xxs),
                OmiButton.tertiary(
                  key: const Key('live_preview_turn_on_live_text'),
                  label: l10n.livePreviewTurnOnLiveText,
                  size: OmiButtonSize.compact,
                  onPressed: () => openAppSettings(),
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
