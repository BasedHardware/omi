import 'package:flutter/material.dart';

import 'package:omi/pages/memories/widgets/memory_graph_page.dart';
import 'package:omi/utils/l10n_extensions.dart';

class OnboardingKnowledgeGraphStep extends StatelessWidget {
  final VoidCallback onContinue;

  const OnboardingKnowledgeGraphStep({super.key, required this.onContinue});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: Colors.black,
      width: double.infinity,
      height: double.infinity,
      child: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(24, 16, 24, 24),
          child: Column(
            children: [
              const SizedBox(height: 12),
              Text(
                context.l10n.onboardingWhatIKnowAboutYouTitle,
                textAlign: TextAlign.center,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 30,
                  fontWeight: FontWeight.bold,
                  height: 1.2,
                  fontFamily: 'Manrope',
                ),
              ),
              const SizedBox(height: 10),
              Text(
                context.l10n.onboardingWhatIKnowAboutYouDescription,
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.65),
                  fontSize: 16,
                  height: 1.4,
                  fontFamily: 'Manrope',
                ),
              ),
              const SizedBox(height: 20),
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(24),
                  child: const MemoryGraphPage(
                    embedded: true,
                    trackOpenEvent: false,
                    showAppBar: false,
                    showShareButton: false,
                    autoRebuildIfEmpty: true,
                    hideRebuildButtonWhenEmpty: true,
                    initialZoom: 0.72,
                  ),
                ),
              ),
              const SizedBox(height: 20),
              SizedBox(
                width: double.infinity,
                height: 56,
                child: ElevatedButton(
                  onPressed: onContinue,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.white,
                    foregroundColor: Colors.black,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(28)),
                    elevation: 0,
                  ),
                  child: Text(
                    context.l10n.continueAction,
                    style: const TextStyle(fontSize: 18, fontWeight: FontWeight.w600, fontFamily: 'Manrope'),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
