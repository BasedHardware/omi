import 'package:flutter/material.dart';

import 'package:omi/services/live_preview/live_preview_controller.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// The live transcript surface for a local-preview session: provisional,
/// on-device text that the batch transcript replaces. Words the recognizer may
/// still revise are drawn in secondary text; settled words in primary text. One
/// unlabeled voice, as for every on-device engine (contract §9): no speakers.
///
/// With no on-device engine it is a calm "Transcribing…" state, not an error
/// and not a setup prompt.
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
        LivePreviewPhase.unavailable => const _Transcribing(),
        LivePreviewPhase.starting => _PreviewFrame(child: _Waiting(text: context.l10n.livePreviewStarting)),
        _ => _PreviewFrame(
            child: preview.lines.isEmpty
                ? _Waiting(text: context.l10n.livePreviewListening, spinner: false)
                : _Lines(lines: preview.lines, bottomInset: bottomInset),
          ),
      },
    );
  }
}

class _PreviewFrame extends StatelessWidget {
  const _PreviewFrame({required this.child});

  final Widget child;

  @override
  Widget build(BuildContext context) {
    return Column(
      key: const Key('live_preview_transcript'),
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.sm, OmiSpacing.md, OmiSpacing.xs),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                context.l10n.livePreviewLabel,
                key: const Key('live_preview_label'),
                style: OmiType.footnote.copyWith(color: OmiColors.textSecondary, fontWeight: FontWeight.w600),
              ),
              const SizedBox(height: OmiSpacing.xxs),
              Text(
                context.l10n.livePreviewExplanation,
                style: OmiType.footnote.copyWith(color: OmiColors.textTertiary),
              ),
            ],
          ),
        ),
        Expanded(child: child),
      ],
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

class _Transcribing extends StatelessWidget {
  const _Transcribing();

  @override
  Widget build(BuildContext context) {
    return Center(
      key: const Key('live_preview_transcribing'),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxl),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const OmiSpinner(size: OmiSpinnerSize.small),
            const SizedBox(height: OmiSpacing.md),
            Text(context.l10n.livePreviewTranscribingTitle, textAlign: TextAlign.center, style: OmiType.headline),
            const SizedBox(height: OmiSpacing.xs),
            Text(
              context.l10n.livePreviewTranscribingMessage,
              textAlign: TextAlign.center,
              style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
            ),
          ],
        ),
      ),
    );
  }
}
