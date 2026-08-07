import 'package:flutter/material.dart';

import 'package:omi/pages/conversations/widgets/daily_summaries_list.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// Full recap history.
///
/// Recaps used to be a *mode* of the conversations page — a chip swapped the
/// whole list out. They are now a carousel at the top of that page, and this is
/// where "View All" goes, so the paged list and swipe-to-delete keep a home.
class DailyRecapsPage extends StatelessWidget {
  const DailyRecapsPage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Theme.of(context).colorScheme.primary,
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.primary,
        elevation: 0,
        title: Text(
          context.l10n.dailyRecaps,
          style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.w600),
        ),
      ),
      body: const CustomScrollView(slivers: [DailySummariesList()]),
    );
  }
}
