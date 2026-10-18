import 'package:flutter/material.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Quiet, independently expandable provenance for one summary section.
class ConversationQuoteTimestamps extends StatefulWidget {
  final List<String> sourceIDs;
  final List<TranscriptSegment> transcriptSegments;
  final ValueChanged<String> onOpenSource;

  const ConversationQuoteTimestamps({
    super.key,
    required this.sourceIDs,
    required this.transcriptSegments,
    required this.onOpenSource,
  });

  @override
  State<ConversationQuoteTimestamps> createState() => _ConversationQuoteTimestampsState();
}

class _ConversationQuoteTimestampsState extends State<ConversationQuoteTimestamps> {
  bool _expanded = false;

  String _spokenTime(double start) {
    final l10n = context.l10n;
    final total = start.floor();
    final hours = total ~/ 3600;
    final minutes = (total % 3600) ~/ 60;
    final seconds = total % 60;
    final duration = total < 3600
        ? OmiDuration.long(total, l10n)
        : [
            hours == 1 ? l10n.timeHourSingular(hours) : l10n.timeHoursPlural(hours),
            minutes == 1 ? l10n.timeMinSingular(minutes) : l10n.timeMinsPlural(minutes),
            seconds == 1 ? l10n.timeSecsSingular(seconds) : l10n.timeSecsPlural(seconds),
          ].join(', ');
    return l10n.quoteJumpToTime(duration);
  }

  @override
  Widget build(BuildContext context) {
    final segments = {for (final segment in widget.transcriptSegments) segment.id: segment};
    final sources = widget.sourceIDs.toSet().where((id) {
      final start = segments[id]?.start;
      return id.isNotEmpty && start != null && start.isFinite && start >= 0;
    }).toList();
    if (sources.isEmpty) return const SizedBox.shrink();
    final visible = _expanded ? sources : sources.take(3).toList();
    final style = OmiType.caption.copyWith(
      color: OmiColors.textTertiary,
      fontFeatures: const [FontFeature.tabularFigures()],
    );
    Widget action(String label, String semantics, String key, VoidCallback onPressed) => Semantics(
          label: semantics,
          button: true,
          onTap: onPressed,
          excludeSemantics: true,
          child: TextButton(
            key: ValueKey(key),
            onPressed: onPressed,
            style: TextButton.styleFrom(
              foregroundColor: OmiColors.textTertiary,
              minimumSize: const Size(44, 44),
              padding: const EdgeInsets.symmetric(horizontal: OmiSpacing.xxs),
              textStyle: style,
            ),
            child: Text(label, style: style),
          ),
        );
    return Align(
      alignment: AlignmentDirectional.centerStart,
      child: Wrap(
        crossAxisAlignment: WrapCrossAlignment.center,
        children: [
          for (var index = 0; index < visible.length; index++)
            Row(mainAxisSize: MainAxisSize.min, children: [
              ExcludeSemantics(
                  child: index == 0
                      ? Icon(Icons.play_arrow_rounded, size: 12, color: OmiColors.textTertiary)
                      : Text('·', style: style)),
              action(OmiDuration.offset(segments[visible[index]]!.start), _spokenTime(segments[visible[index]]!.start),
                  'quote-time-${visible[index]}', () => widget.onOpenSource(visible[index])),
            ]),
          if (!_expanded && sources.length > 3)
            Row(mainAxisSize: MainAxisSize.min, children: [
              ExcludeSemantics(child: Text('·', style: style)),
              action(
                  context.l10n.quoteMoreTimestamps(sources.length - 3),
                  context.l10n.quoteMoreTimestamps(sources.length - 3),
                  'quote-times-more',
                  () => setState(() => _expanded = true)),
            ]),
        ],
      ),
    );
  }
}
