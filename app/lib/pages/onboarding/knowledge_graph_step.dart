import 'package:flutter/material.dart';

import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/ui/ui.dart';
import 'package:omi/utils/l10n_extensions.dart';

class OnboardingKnowledgeGraphStep extends StatelessWidget {
  final VoidCallback onContinue;

  const OnboardingKnowledgeGraphStep({super.key, required this.onContinue});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: OmiColors.surface0,
      width: double.infinity,
      height: double.infinity,
      child: SafeArea(
        child: Padding(
          // Clear of the progress dots and back button drawn over the top of every step.
          padding: const EdgeInsets.fromLTRB(OmiSpacing.xl, 60, OmiSpacing.xl, OmiSpacing.xl),
          child: Column(
            children: [
              Semantics(
                header: true,
                child: Text(
                  context.l10n.onboardingWhatIKnowAboutYouTitle,
                  textAlign: TextAlign.center,
                  style: OmiType.title1.copyWith(height: 1.2),
                ),
              ),
              const SizedBox(height: 10),
              Text(
                context.l10n.onboardingWhatIKnowAboutYouDescription,
                textAlign: TextAlign.center,
                style: OmiType.callout.copyWith(color: OmiColors.textSecondary, height: 1.4),
              ),
              const SizedBox(height: OmiSpacing.lg),
              const Expanded(
                child: ClipRRect(
                  borderRadius: OmiRadius.xlAll,
                  child: MemoryGraphPage(
                    embedded: true,
                    trackOpenEvent: false,
                    showAppBar: false,
                    showShareButton: false,
                    initialZoom: 0.72,
                  ),
                ),
              ),
              const SizedBox(height: OmiSpacing.lg),
              OmiButton(
                key: const Key('onboarding_knowledge_graph_continue'),
                label: context.l10n.continueButton,
                expand: true,
                onPressed: () {
                  OmiHaptics.selection();
                  onContinue();
                },
              ),
            ],
          ),
        ),
      ),
    );
  }
}
