import 'package:flutter/material.dart';

import 'package:omi/utils/l10n_extensions.dart';

/// Compact card with the topics to cover while recording a speech profile,
/// shown all at once instead of one question at a time. They mirror the
/// backend's ONBOARDING_QUESTIONS.
class SpeechTopicsCard extends StatelessWidget {
  const SpeechTopicsCard({super.key});

  @override
  Widget build(BuildContext context) {
    final topics = [
      context.l10n.speechProfileTopicLocation,
      context.l10n.speechProfileTopicWork,
      context.l10n.speechProfileTopicGoal,
    ];
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(14, 10, 14, 12),
      decoration: BoxDecoration(
        border: Border.all(color: Colors.white, width: 1.2),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(
            context.l10n.answerWithYourVoice,
            style: TextStyle(color: Colors.white.withValues(alpha: 0.7), fontSize: 13, fontWeight: FontWeight.w600),
          ),
          const SizedBox(height: 6),
          for (final topic in topics)
            Padding(
              padding: const EdgeInsets.only(top: 3),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Padding(
                    padding: EdgeInsets.only(top: 7, right: 8),
                    child: CircleAvatar(radius: 2, backgroundColor: Colors.white),
                  ),
                  Expanded(
                    child: Text(
                      topic,
                      style: const TextStyle(color: Colors.white, fontSize: 15, height: 1.3),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
