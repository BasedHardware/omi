import 'package:flutter/material.dart';

import 'package:font_awesome_flutter/font_awesome_flutter.dart';
import 'package:provider/provider.dart';

import 'package:omi/providers/conversation_provider.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';
import 'package:omi/utils/platform/platform_manager.dart';
import 'package:omi/widgets/calendar_date_picker_sheet.dart';

/// The label of the conversation date filter: one date ("Sep 3, 2026") or a range
/// ("Sep 1, 2026 – Sep 7, 2026"), in the reader's locale.
String conversationDateFilterLabel(OmiDateFormat dates, DateTime start, DateTime? end) {
  final last = end ?? start;
  final sameDay = start.year == last.year && start.month == last.month && start.day == last.day;
  return sameDay ? dates.date(start) : '${dates.date(start)} – ${dates.date(last)}';
}

/// The active conversation date filter as a removable chip (hub audit #23). Tapping it reopens the
/// picker; its X clears the filter. Nothing is drawn while no date filter is set.
class ConversationDateFilterChip extends StatelessWidget {
  const ConversationDateFilterChip({super.key});

  @override
  Widget build(BuildContext context) {
    final range = context.select<ConversationProvider, (DateTime?, DateTime?)>(
      (p) => (p.selectedStartDate, p.selectedEndDate),
    );
    final start = range.$1;
    if (start == null) return const SizedBox.shrink();
    final l10n = context.l10n;
    final label = conversationDateFilterLabel(OmiDateFormat.of(context), start, range.$2);
    return Padding(
      padding: const EdgeInsets.fromLTRB(OmiSpacing.md, OmiSpacing.xxs, OmiSpacing.md, OmiSpacing.xxs),
      child: Align(
        alignment: AlignmentDirectional.centerStart,
        child: InputChip(
          key: const Key('conversation_date_filter_chip'),
          // The header's date-filter button draws the same glyph.
          avatar: const FaIcon(FontAwesomeIcons.calendarDay, size: 14, color: OmiColors.textSecondary),
          label: Text(label, style: OmiType.footnote),
          tooltip: l10n.filterByDate,
          backgroundColor: OmiColors.surface1,
          side: const BorderSide(color: OmiColors.border),
          shape: const StadiumBorder(),
          deleteIcon: const Icon(Icons.close, size: 16, color: OmiColors.textSecondary),
          deleteButtonTooltipMessage: l10n.removeFilter,
          onPressed: () => showConversationDateRangePicker(context),
          onDeleted: () async {
            await context.read<ConversationProvider>().clearDateFilter();
            PlatformManager.instance.analytics.calendarFilterCleared();
          },
        ),
      ),
    );
  }
}
