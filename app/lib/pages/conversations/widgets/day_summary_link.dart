import 'package:flutter/material.dart';

import 'package:omi/backend/http/api/daily_summary_creation.dart';
import 'package:omi/backend/http/api_result.dart';
import 'package:omi/backend/schema/daily_summary.dart';
import 'package:omi/pages/settings/daily_summary_detail_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

typedef DaySummaryOpener = Future<ApiResult<DailySummary>> Function(String date);

/// A finished day's label on the v3 Home: "Yesterday ›". A tap opens that day's summary; the
/// server returns the stored one or writes it. Today has no link, since its summary would repeat
/// the rows under it.
class DaySummaryHeader extends StatefulWidget {
  const DaySummaryHeader({super.key, required this.date, required this.isFirst, this.open, this.onOpened});

  final DateTime date;
  final bool isFirst;
  final DaySummaryOpener? open;

  /// Test seam: receives the summary instead of pushing its page.
  final ValueChanged<DailySummary>? onOpened;

  static String dateKey(DateTime date) => '${date.year.toString().padLeft(4, '0')}-'
      '${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';

  @override
  State<DaySummaryHeader> createState() => _DaySummaryHeaderState();
}

class _DaySummaryHeaderState extends State<DaySummaryHeader> {
  bool _busy = false;

  Future<void> _open() async {
    if (_busy) return;
    OmiHaptics.selection();
    setState(() => _busy = true);
    try {
      final result =
          await (widget.open ?? const DailySummaryCreationApi().create)(DaySummaryHeader.dateKey(widget.date));
      if (!mounted) return;
      switch (result) {
        case ApiSuccess<DailySummary>(:final data) when widget.onOpened != null:
          widget.onOpened!(data);
        case ApiSuccess<DailySummary>(:final data):
          await Navigator.of(context).push(MaterialPageRoute<void>(
            builder: (_) => DailySummaryDetailPage(summaryId: data.id, summary: data),
          ));
        case ApiFailure<DailySummary>(:final problem):
          OmiFeedback.error(
            context,
            switch (problem.statusCode) {
              400 => context.l10n.recapRegenerateNoConversations,
              409 || 429 => context.l10n.recapRegenerateCooldown,
              _ => problem.kind == ApiProblemKind.transport
                  ? context.l10n.checkConnectionTryAgain
                  : context.l10n.somethingWentWrong,
            },
          );
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final label = OmiDateFormat.of(context).dayHeader(widget.date);
    return Padding(
      padding: EdgeInsets.fromLTRB(12, widget.isFirst ? 0 : 6, 16, 0),
      child: Semantics(
        header: true,
        button: true,
        label: '$label, ${context.l10n.daySummary}',
        excludeSemantics: true,
        onTap: _open,
        child: Align(
          alignment: AlignmentDirectional.centerStart,
          child: InkWell(
            key: ValueKey('day_summary_header_${DaySummaryHeader.dateKey(widget.date)}'),
            onTap: _open,
            borderRadius: OmiRadius.mdAll,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(8, 4, 4, 4),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(label, style: OmiType.body.copyWith(fontWeight: FontWeight.w600)),
                  const SizedBox(width: 2),
                  SizedBox.square(
                    dimension: 20,
                    child: _busy
                        ? const Center(child: OmiSpinner(size: OmiSpinnerSize.small))
                        : Icon(Icons.chevron_right_rounded, size: 20, color: OmiColors.textTertiary),
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
