import 'package:flutter/material.dart';

import 'package:nooto_v2/theme/app_theme.dart';
import '../models/study_data.dart';
import 'study_screen.dart';

/// Compact card that shows a preview of the study session.
/// Tapping navigates to the full-screen [StudyScreen].
class StudyCard extends StatelessWidget {
  final StudyData data;

  const StudyCard({super.key, required this.data});

  void _openStudyScreen(BuildContext context) {
    Navigator.of(context).push(MaterialPageRoute(builder: (_) => StudyScreen(data: data)));
  }

  @override
  Widget build(BuildContext context) {
    if (data.isEmpty) {
      return const SizedBox.shrink();
    }

    return Padding(
      padding: const EdgeInsets.only(top: AppStyles.spacingS, bottom: AppStyles.spacingM),
      child: InkWell(
        onTap: () => _openStudyScreen(context),
        borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
        child: Container(
          padding: const EdgeInsets.all(AppStyles.spacingL),
          decoration: BoxDecoration(
            color: AppColors.backgroundSecondary,
            borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
            border: Border.all(color: AppColors.brandPrimary.withValues(alpha: 0.3), width: 1),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(AppStyles.spacingS),
                    decoration: BoxDecoration(
                      color: AppColors.brandPrimary.withValues(alpha: 0.2),
                      borderRadius: BorderRadius.circular(AppStyles.radiusMedium),
                    ),
                    child: const Icon(Icons.school_outlined, color: AppColors.brandPrimary, size: 20),
                  ),
                  const SizedBox(width: AppStyles.spacingM),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          data.title,
                          style: const TextStyle(
                            color: AppColors.textPrimary,
                            fontSize: 16,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                        const SizedBox(height: 2),
                        const Text(
                          'Tap to view study set',
                          style: TextStyle(color: AppColors.textTertiary, fontSize: 12),
                        ),
                      ],
                    ),
                  ),
                  Container(
                    padding: const EdgeInsets.all(AppStyles.spacingS),
                    decoration: BoxDecoration(
                      color: AppColors.backgroundTertiary,
                      borderRadius: BorderRadius.circular(AppStyles.radiusXLarge),
                    ),
                    child: const Icon(Icons.arrow_forward_rounded, color: AppColors.textPrimary, size: 18),
                  ),
                ],
              ),
              const SizedBox(height: AppStyles.spacingL),
              Row(
                children: [
                  if (data.flashcardCount > 0)
                    _QuestionChip(
                      icon: Icons.flip,
                      label: '${data.flashcardCount} flashcards',
                      color: AppColors.successColor,
                    ),
                  if (data.flashcardCount > 0 && data.abcCount > 0) const SizedBox(width: AppStyles.spacingS),
                  if (data.abcCount > 0)
                    _QuestionChip(
                      icon: Icons.quiz_outlined,
                      label: '${data.abcCount} questions',
                      color: AppColors.warningColor,
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

class _QuestionChip extends StatelessWidget {
  final IconData icon;
  final String label;
  final Color color;

  const _QuestionChip({required this.icon, required this.label, required this.color});

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(AppStyles.radiusXLarge),
        border: Border.all(color: color.withValues(alpha: 0.3), width: 1),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.w500),
          ),
        ],
      ),
    );
  }
}
