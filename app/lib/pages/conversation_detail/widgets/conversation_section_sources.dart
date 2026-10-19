import 'package:flutter/material.dart';
import 'package:omi/backend/schema/transcript_segment.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Quiet provenance for one summary section: a heading-row control that lists the section's
/// supporting transcript moments in a sheet, so nothing interrupts the summary prose itself.
class ConversationSectionSourcesButton extends StatelessWidget {
  final String heading;
  final List<String> sourceIDs;
  final List<TranscriptSegment> transcriptSegments;
  final ValueChanged<String> onOpenSource;

  const ConversationSectionSourcesButton({
    super.key,
    required this.heading,
    required this.sourceIDs,
    required this.transcriptSegments,
    required this.onOpenSource,
  });

  /// The cited segments that exist in the loaded transcript, deduplicated in citation order.
  static List<TranscriptSegment> resolve(List<String> sourceIDs, List<TranscriptSegment> transcriptSegments) {
    final segments = {for (final segment in transcriptSegments) segment.id: segment};
    return sourceIDs
        .toSet()
        .where((id) => id.isNotEmpty)
        .map((id) => segments[id])
        .whereType<TranscriptSegment>()
        .where((segment) => segment.start.isFinite && segment.start >= 0)
        .toList();
  }

  @override
  Widget build(BuildContext context) {
    final sources = resolve(sourceIDs, transcriptSegments);
    if (sources.isEmpty) return const SizedBox.shrink();
    return OmiIconButton(
      key: const ValueKey('section-sources'),
      icon: const Icon(Icons.graphic_eq_rounded, size: 18),
      label: context.l10n.quoteShowSources,
      color: OmiColors.textTertiary,
      onPressed: () => showOmiSheet<void>(
        context: context,
        title: heading.trim().isEmpty ? null : heading.trim(),
        builder: (sheetContext) => _SectionSourcesList(
          sources: sources,
          onOpenSource: (id) {
            Navigator.of(sheetContext).pop();
            onOpenSource(id);
          },
        ),
      ),
    );
  }
}

class _SectionSourcesList extends StatelessWidget {
  final List<TranscriptSegment> sources;
  final ValueChanged<String> onOpenSource;

  const _SectionSourcesList({required this.sources, required this.onOpenSource});

  String _spokenTime(BuildContext context, double start) {
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
    final timeStyle = OmiType.footnote.copyWith(
      color: OmiColors.textTertiary,
      fontFeatures: const [FontFeature.tabularFigures()],
    );
    // The sheet shell already bounds this in a Flexible; a long list scrolls inside it.
    return SingleChildScrollView(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final source in sources)
            Semantics(
              label: _spokenTime(context, source.start),
              button: true,
              excludeSemantics: true,
              child: InkWell(
                key: ValueKey('section-source-${source.id}'),
                onTap: () => onOpenSource(source.id),
                borderRadius: BorderRadius.circular(OmiRadius.sm),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(minHeight: kOmiMinTapTarget),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: OmiSpacing.xs),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        ConstrainedBox(
                          // Fits m:ss and h:mm:ss; a longer offset widens the column instead of overflowing.
                          constraints: const BoxConstraints(minWidth: 56),
                          child: Padding(
                            padding: const EdgeInsetsDirectional.only(end: OmiSpacing.xs),
                            child: Text(OmiDuration.offset(source.start), style: timeStyle),
                          ),
                        ),
                        Expanded(
                          child: Text(
                            source.text.trim(),
                            maxLines: 3,
                            overflow: TextOverflow.ellipsis,
                            style: OmiType.subhead.copyWith(color: OmiColors.textSecondary),
                          ),
                        ),
                        Icon(Icons.play_arrow_rounded, size: 20, color: OmiColors.textTertiary),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          const SizedBox(height: OmiSpacing.sm),
        ],
      ),
    );
  }
}
