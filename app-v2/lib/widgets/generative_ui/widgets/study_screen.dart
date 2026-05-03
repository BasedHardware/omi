import 'package:flutter/material.dart';

import 'package:nooto_v2/theme/app_theme.dart';
import '../models/study_data.dart';

/// Read-only list view of a study session — the legacy `/app` ships an
/// interactive flashcard / multiple-choice game; app-v2 ports the data
/// pipeline and renders the questions + answers in a flat list. Adding
/// the gamified UI is deferred until the use case justifies it.
class StudyScreen extends StatelessWidget {
  final StudyData data;

  const StudyScreen({super.key, required this.data});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.backgroundPrimary,
      appBar: AppBar(
        backgroundColor: AppColors.backgroundPrimary,
        elevation: 0,
        title: Text(
          data.title,
          style: const TextStyle(fontSize: 17, fontWeight: FontWeight.w600, color: AppColors.textPrimary),
        ),
      ),
      body: ListView.separated(
        padding: const EdgeInsets.fromLTRB(AppStyles.spacingL, 0, AppStyles.spacingL, AppStyles.spacingXL),
        itemCount: data.questions.length,
        separatorBuilder: (_, _) => const SizedBox(height: AppStyles.spacingL),
        itemBuilder: (context, index) {
          final q = data.questions[index];
          return _QuestionCard(question: q, index: index + 1);
        },
      ),
    );
  }
}

class _QuestionCard extends StatelessWidget {
  const _QuestionCard({required this.question, required this.index});
  final StudyQuestionData question;
  final int index;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(AppStyles.spacingL),
      decoration: BoxDecoration(
        color: AppColors.backgroundSecondary,
        borderRadius: BorderRadius.circular(AppStyles.radiusLarge),
        border: Border.all(color: Colors.white.withValues(alpha: 0.06)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Q$index',
            style: const TextStyle(
              color: AppColors.brandPrimary,
              fontSize: 11,
              fontWeight: FontWeight.w600,
              letterSpacing: 0.4,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            question.question,
            style: const TextStyle(color: AppColors.textPrimary, fontSize: 16, fontWeight: FontWeight.w500),
          ),
          const SizedBox(height: AppStyles.spacingM),
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Icon(Icons.check_circle, size: 16, color: AppColors.successColor),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  question.correctAnswer,
                  style: const TextStyle(color: AppColors.textSecondary, fontSize: 14, height: 1.4),
                ),
              ),
            ],
          ),
          if (question.wrongOptions.isNotEmpty) ...[
            const SizedBox(height: AppStyles.spacingS),
            for (final w in question.wrongOptions)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Icon(Icons.radio_button_unchecked, size: 16, color: AppColors.textQuaternary),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(w, style: const TextStyle(color: AppColors.textTertiary, fontSize: 14, height: 1.4)),
                    ),
                  ],
                ),
              ),
          ],
        ],
      ),
    );
  }
}
