import 'package:flutter/material.dart';

import 'package:nooto_v2/theme/app_theme.dart';
import '../models/story_briefing_data.dart';
import 'story_briefing_screen.dart';

/// Compact card that shows a preview of the story briefing.
/// Tapping navigates to the full-screen [StoryBriefingScreen].
class StoryBriefingCard extends StatelessWidget {
  final StoryBriefingData data;

  const StoryBriefingCard({super.key, required this.data});

  void _openStoryBriefing(BuildContext context) {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => StoryBriefingScreen(data: data)));
  }

  @override
  Widget build(BuildContext context) {
    if (data.isEmpty) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.only(top: AppStyles.spacingS, bottom: AppStyles.spacingM),
      child: InkWell(
        onTap: () => _openStoryBriefing(context),
        borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
        child: Container(
          padding: const EdgeInsets.all(AppStyles.spacingL),
          decoration: BoxDecoration(
            color: AppColors.backgroundSecondary,
            borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
            border: Border.all(color: Colors.white.withValues(alpha: 0.06), width: 1),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: const [
                  Icon(Icons.article_outlined, color: AppColors.textTertiary, size: 18),
                  SizedBox(width: AppStyles.spacingS),
                  Expanded(
                    child: Text(
                      'Story Briefing',
                      style: TextStyle(color: AppColors.textPrimary, fontSize: 16, fontWeight: FontWeight.w600),
                    ),
                  ),
                  Icon(Icons.chevron_right, color: AppColors.textTertiary, size: 20),
                ],
              ),
              const SizedBox(height: AppStyles.spacingM),
              Text(data.summary, style: const TextStyle(color: AppColors.textTertiary, fontSize: 13)),
              const SizedBox(height: AppStyles.spacingL),
              Wrap(
                spacing: AppStyles.spacingS,
                runSpacing: AppStyles.spacingS,
                children: [
                  if (data.hasTimeline)
                    _SectionChip(icon: Icons.timeline, label: '${data.timeline!.events.length} events'),
                  if (data.hasQuotes)
                    _SectionChip(icon: Icons.format_quote, label: '${data.quoteBoard!.quotes.length} quotes'),
                  if (data.hasFollowups)
                    _SectionChip(icon: Icons.checklist_rounded, label: '${data.followups!.items.length} follow-ups'),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SectionChip extends StatelessWidget {
  final IconData icon;
  final String label;

  const _SectionChip({required this.icon, required this.label});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: AppColors.backgroundTertiary,
        borderRadius: BorderRadius.circular(AppStyles.radiusXLarge),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: AppColors.textTertiary),
          const SizedBox(width: 6),
          Text(
            label,
            style: const TextStyle(color: AppColors.textTertiary, fontSize: 12, fontWeight: FontWeight.w500),
          ),
        ],
      ),
    );
  }
}
