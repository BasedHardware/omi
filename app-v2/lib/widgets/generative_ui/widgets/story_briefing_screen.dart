import 'package:flutter/material.dart';

import 'package:nooto_v2/theme/app_theme.dart';
import '../models/story_briefing_data.dart';
import 'followups_widget.dart';
import 'quote_board_widget.dart';
import 'timeline_widget.dart';

/// Full-screen view of an aggregated story briefing — timeline events,
/// quotes, and follow-ups stacked together.
///
/// Simplified from the legacy `/app` version (which had segment-tab toggling,
/// scroll-aware sticky headers, and a hero animation). app-v2 ships the
/// flat scroll: title, sections, done. Adding the upper-end interactivity is
/// deferred until the use case actually justifies it.
class StoryBriefingScreen extends StatelessWidget {
  final StoryBriefingData data;

  const StoryBriefingScreen({super.key, required this.data});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.backgroundPrimary,
      appBar: AppBar(
        backgroundColor: AppColors.backgroundPrimary,
        elevation: 0,
        title: const Text(
          'Story Briefing',
          style: TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
        ),
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(AppStyles.spacingL, 0, AppStyles.spacingL, AppStyles.spacingXL),
        children: [
          if (data.hasTimeline) TimelineWidget(data: data.timeline!),
          if (data.hasQuotes) QuoteBoardWidget(data: data.quoteBoard!),
          if (data.hasFollowups) FollowupsWidget(data: data.followups!),
        ],
      ),
    );
  }
}
