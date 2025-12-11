import 'package:flutter/material.dart';
import '../models/story_briefing_data.dart';
import 'story_briefing_screen.dart';

/// Compact card that shows a preview of the story briefing
/// Tapping navigates to the full-screen StoryBriefingScreen
class StoryBriefingCard extends StatelessWidget {
  final StoryBriefingData data;

  const StoryBriefingCard({
    super.key,
    required this.data,
  });

  void _openStoryBriefing(BuildContext context) {
    Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) => StoryBriefingScreen(data: data),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (data.isEmpty) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.only(top: 8, bottom: 12),
      child: InkWell(
        onTap: () => _openStoryBriefing(context),
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: Colors.white.withOpacity(0.05),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: Colors.white.withOpacity(0.1),
              width: 1,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              // Title row with icon
              Row(
                children: [
                  Icon(
                    Icons.article_outlined,
                    color: Colors.white.withOpacity(0.6),
                    size: 18,
                  ),
                  const SizedBox(width: 8),
                  const Expanded(
                    child: Text(
                      'Story Briefing',
                      style: TextStyle(
                        color: Colors.white,
                        fontSize: 16,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  Icon(
                    Icons.chevron_right,
                    color: Colors.white.withOpacity(0.5),
                    size: 20,
                  ),
                ],
              ),

              const SizedBox(height: 12),

              // Summary
              Text(
                data.summary,
                style: TextStyle(
                  color: Colors.white.withOpacity(0.7),
                  fontSize: 13,
                ),
              ),

              const SizedBox(height: 16),

              // Section previews
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  if (data.hasTimeline)
                    _SectionChip(
                      icon: Icons.timeline,
                      label: '${data.timeline!.events.length} events',
                    ),
                  if (data.hasQuotes)
                    _SectionChip(
                      icon: Icons.format_quote,
                      label: '${data.quoteBoard!.quotes.length} quotes',
                    ),
                  if (data.hasFollowups)
                    _SectionChip(
                      icon: Icons.checklist_rounded,
                      label: '${data.followups!.items.length} follow-ups',
                    ),
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

  const _SectionChip({
    required this.icon,
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.white.withOpacity(0.08),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(
            icon,
            size: 14,
            color: Colors.white.withOpacity(0.6),
          ),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(
              color: Colors.white.withOpacity(0.7),
              fontSize: 12,
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }
}
