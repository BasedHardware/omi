import 'package:flutter/material.dart';

import 'package:omi/backend/preferences.dart';
import 'package:omi/pages/onboarding/widgets/knowledge_preview.dart';
import 'package:omi/pages/onboarding/widgets/onboarding_card.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

/// "Here is what I know about you" (v2 `Knows`): a picture of the map Omi builds — the reader at the
/// centre and the kinds of things it learns around them — since a new account has nothing to show
/// yet. The standard step layout, so Continue sits where it does on every other step.
class OnboardingKnowledgeGraphStep extends StatelessWidget {
  final VoidCallback onContinue;

  const OnboardingKnowledgeGraphStep({super.key, required this.onContinue});

  @override
  Widget build(BuildContext context) {
    final l10n = context.l10n;
    final name = SharedPreferencesUtil().givenName.trim();
    return ColoredBox(
      color: OmiColors.surface0,
      child: OnboardingStep(
        card: OnboardingCard(
          content: [
            OnboardingHeader(title: l10n.onboardingWhatIKnowAboutYouTitle),
            const SizedBox(height: OmiSpacing.lg),
            OnboardingKnowledgePreview(
              center: name.isEmpty ? l10n.you : name,
              topics: [l10n.categoryProductivity, l10n.people, l10n.categoryHealth, l10n.goals],
            ),
            const SizedBox(height: OmiSpacing.lg),
            Padding(
              padding: OnboardingCard.textInset,
              child: OmiBalancedText(
                l10n.onboardingWhatIKnowAboutYouDescription,
                style: OmiType.body.copyWith(color: OmiColors.textSecondary, height: 1.35),
              ),
            ),
          ],
          footer: [
            OmiButton(
              key: const Key('onboarding_knowledge_graph_continue'),
              label: l10n.continueButton,
              expand: true,
              onPressed: () {
                OmiHaptics.selection();
                onContinue();
              },
            ),
          ],
        ),
      ),
    );
  }
}
